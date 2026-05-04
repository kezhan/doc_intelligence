"""
TODO-008 — Detection of fragmented tables belonging to the same logical table
TODO-009 — PDF → Excel pipeline via table extraction
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pdfplumber


# ── TODO-008 ─────────────────────────────────────────────────────────────────

@pd.api.extensions.register_dataframe_accessor("table_meta")
class _TableMeta:
    """Lightweight metadata carrier attached to extracted tables."""
    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df


def extract_all_tables(pdf_path: str | Path) -> list[dict[str, Any]]:
    """
    Extract every table from a PDF, with page and position metadata.

    Returns a list of dicts:
        {"page": int, "bbox": tuple, "df": pd.DataFrame}
    """
    results: list[dict[str, Any]] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables():
                if not table:
                    continue
                df = _raw_table_to_df(table)
                if df.empty:
                    continue
                results.append({
                    "page": page_num,
                    "bbox": page.bbox,
                    "df": df,
                })

    return results


def detect_fragmented_tables(
    pdf_path: str | Path,
    *,
    column_similarity_threshold: float = 0.75,
) -> list[pd.DataFrame]:
    """
    TODO-008 — Group cross-page table fragments into single logical tables.

    Input : path to a multi-page PDF
    Output: list of consolidated DataFrames (one per logical table)

    Two fragments are merged when their column sets match above the threshold.
    """
    fragments = extract_all_tables(pdf_path)
    if not fragments:
        return []

    groups: list[list[dict[str, Any]]] = []

    for frag in fragments:
        placed = False
        for group in groups:
            if _columns_compatible(group[-1]["df"], frag["df"], column_similarity_threshold):
                group.append(frag)
                placed = True
                break
        if not placed:
            groups.append([frag])

    consolidated: list[pd.DataFrame] = []
    for group in groups:
        dfs = [g["df"] for g in group]
        merged = pd.concat(dfs, ignore_index=True)
        merged = merged.dropna(how="all").reset_index(drop=True)
        consolidated.append(merged)

    return consolidated


# ── TODO-009 ─────────────────────────────────────────────────────────────────

def pdf_to_excel(pdf_path: str | Path, output_path: str | Path | None = None) -> Path:
    """
    TODO-009 — Full PDF → Excel pipeline.

    Input : path to a PDF containing tables
    Output: .xlsx file with one sheet per logical table
    """
    pdf_path = Path(pdf_path)
    if output_path is None:
        output_path = pdf_path.with_suffix(".xlsx")
    else:
        output_path = Path(output_path)

    tables = detect_fragmented_tables(pdf_path)

    if not tables:
        # Write an empty workbook to signal successful run with no tables found
        pd.DataFrame({"info": ["No tables found in this PDF"]}).to_excel(
            str(output_path), index=False, sheet_name="info"
        )
        return output_path

    with pd.ExcelWriter(str(output_path), engine="openpyxl") as writer:
        for idx, table in enumerate(tables, start=1):
            sheet_name = f"Table_{idx}"
            table.to_excel(writer, sheet_name=sheet_name, index=False)

    return output_path


# ── helpers ───────────────────────────────────────────────────────────────────

def _raw_table_to_df(raw: list[list[Any]]) -> pd.DataFrame:
    if not raw:
        return pd.DataFrame()
    header = [str(c) if c is not None else f"col_{i}" for i, c in enumerate(raw[0])]
    rows = raw[1:]
    return pd.DataFrame(rows, columns=header)


def _columns_compatible(df_a: pd.DataFrame, df_b: pd.DataFrame, threshold: float) -> bool:
    """Jaccard similarity between column name sets."""
    cols_a = set(df_a.columns)
    cols_b = set(df_b.columns)
    if not cols_a or not cols_b:
        return False
    # Also accept if same number of columns (unnamed continuation)
    if len(cols_a) == len(cols_b):
        return True
    union = cols_a | cols_b
    intersection = cols_a & cols_b
    return len(intersection) / len(union) >= threshold

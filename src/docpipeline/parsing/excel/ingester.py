"""
TODO-019 — Excel → queryable database conversion (SQLite or Parquet)
"""

from __future__ import annotations

import sqlite3
import re
from pathlib import Path

import pandas as pd


def ingest_excel(
    xlsx_path: str | Path,
    output_path: str | Path | None = None,
    *,
    output_format: str = "sqlite",
) -> Path:
    """
    TODO-019 — Convert an Excel file (single or multi-sheet) to a queryable store.

    Input : path to a .xlsx file
    Output: path to a .db (SQLite) or .parquet file + clean schema

    Each sheet becomes a separate table in SQLite or a separate Parquet file.
    """
    xlsx_path = Path(xlsx_path)
    output_format = output_format.lower()

    if output_format not in ("sqlite", "parquet"):
        raise ValueError("output_format must be 'sqlite' or 'parquet'")

    if output_path is None:
        suffix = ".db" if output_format == "sqlite" else ".parquet"
        output_path = xlsx_path.with_suffix(suffix)
    else:
        output_path = Path(output_path)

    xl = pd.ExcelFile(str(xlsx_path))

    if output_format == "sqlite":
        return _to_sqlite(xl, output_path)
    else:
        return _to_parquet(xl, output_path)


# ── backends ──────────────────────────────────────────────────────────────────

def _to_sqlite(xl: pd.ExcelFile, db_path: Path) -> Path:
    conn = sqlite3.connect(str(db_path))
    try:
        for sheet in xl.sheet_names:
            df = xl.parse(sheet)
            df = _clean_df(df)
            table_name = _safe_name(sheet)
            df.to_sql(table_name, conn, if_exists="replace", index=False)
    finally:
        conn.close()
    return db_path


def _to_parquet(xl: pd.ExcelFile, base_path: Path) -> Path:
    base_path.mkdir(parents=True, exist_ok=True)
    for sheet in xl.sheet_names:
        df = xl.parse(sheet)
        df = _clean_df(df)
        parquet_file = base_path / f"{_safe_name(sheet)}.parquet"
        df.to_parquet(str(parquet_file), index=False)
    return base_path


def _clean_df(df: pd.DataFrame) -> pd.DataFrame:
    """Minimal cleaning: fix column names, drop fully-empty rows/cols."""
    df = df.dropna(how="all").dropna(axis=1, how="all")
    df.columns = [_safe_name(str(c)) for c in df.columns]
    # Infer better dtypes
    df = df.infer_objects()
    return df


def _safe_name(name: str) -> str:
    """Convert an arbitrary string to a safe SQL identifier."""
    name = re.sub(r"[^\w]", "_", name.strip().lower())
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "sheet"

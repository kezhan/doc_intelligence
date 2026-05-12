"""Utilities for writing detected TOC entries back as PDF bookmarks."""

from __future__ import annotations

from pathlib import Path

import fitz
import pandas as pd


def add_dataframe_toc_to_pdf(
    toc_df: pd.DataFrame,
    pdf_path: str | Path,
    output_path: str | Path,
    *,
    clear_existing: bool = True,
) -> int:
    """
    Add bookmarks to a PDF using a DataFrame with ``text`` and ``page_num`` columns.

    Returns the number of bookmarks written.  ``page_num`` is interpreted as the
    displayed PDF page number used by extraction helpers in this package.

    If the DataFrame contains a ``level`` column (e.g. from ``extract_native_toc``
    or ``extract_toc_with_gpt``), bookmark hierarchy is preserved.  Otherwise all
    entries are written at level 1 — matching the flat behaviour of
    ``ai_toc.toc.add_toc.add_dataframe_toc_to_pdf``.
    """
    source = Path(pdf_path)
    if not source.exists():
        raise FileNotFoundError(f"PDF file not found: {source}")

    required_columns = {"text", "page_num"}
    missing_columns = required_columns - set(toc_df.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"TOC DataFrame is missing required columns: {missing}")

    has_level_column = "level" in toc_df.columns

    bookmarks: list[list[int | str]] = []
    for _, row in toc_df.iterrows():
        title = str(row["text"]).strip()
        if not title or pd.isna(row["page_num"]):
            continue

        displayed_page = max(int(row["page_num"]), 1)

        if has_level_column and pd.notna(row["level"]):
            level = max(int(row["level"]), 1)
        else:
            level = 1

        bookmarks.append([level, title, displayed_page])

    with fitz.open(str(source)) as doc:
        if clear_existing:
            doc.set_toc([])
        if bookmarks:
            doc.set_toc(bookmarks)
        doc.save(str(output_path))

    return len(bookmarks)

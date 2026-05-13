"""Internal helpers for TOC dataframe normalisation."""

from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher

import pandas as pd

from .reader import normalize_text

_SECTION_PREFIX_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)[.)]?\s+")
_SECTION_ONLY_RE = re.compile(r"^\s*\d+(?:\.\d+)*[.)]?\s*$")


def infer_toc_level(text: str) -> int:
    """Infer a hierarchy level from a TOC entry title."""
    stripped_text = str(text).strip()
    prefix_match = _SECTION_PREFIX_RE.match(stripped_text)
    if prefix_match:
        return prefix_match.group(1).count(".") + 1
    if _SECTION_ONLY_RE.match(stripped_text):
        return max(stripped_text.count("."), 1)
    return 1


def add_toc_metadata(toc_df: pd.DataFrame) -> pd.DataFrame:
    """Add ``level`` and ``indicator`` columns to a TOC dataframe."""
    if toc_df.empty:
        df = toc_df.copy()
        if "level" not in df.columns:
            df["level"] = pd.Series(dtype="int64")
        if "indicator" not in df.columns:
            df["indicator"] = pd.Series(dtype="object")
        return df

    df = toc_df.copy()
    if "level" not in df.columns:
        title_column = "text" if "text" in df.columns else "title"
        df["level"] = df[title_column].map(infer_toc_level)

    counters: dict[int, int] = {}
    indicators: list[str] = []
    for level_value in df["level"]:
        level = max(int(level_value), 1)
        for counter_level in list(counters):
            if counter_level > level:
                del counters[counter_level]
        counters[level] = counters.get(level, 0) + 1
        indicators.append(
            "L" + ".".join(str(counters[counter_level]) for counter_level in sorted(counters) if counter_level <= level)
        )

    df["level"] = df["level"].astype(int)
    df["indicator"] = indicators
    return df


def add_page_end_column(toc_df: pd.DataFrame, page_column: str = "page") -> pd.DataFrame:
    """Add a best-effort ``page_end`` column based on the next TOC entry."""
    if toc_df.empty:
        df = toc_df.copy()
        if "page_end" not in df.columns:
            df["page_end"] = pd.Series(dtype="Int64")
        return df

    df = toc_df.copy()
    starts = pd.to_numeric(df[page_column], errors="coerce").astype("Int64")
    page_ends: list[int | None] = []
    for index, start_value in enumerate(starts):
        if pd.isna(start_value):
            page_ends.append(None)
            continue
        if index + 1 >= len(starts) or pd.isna(starts.iloc[index + 1]):
            page_ends.append(None)
            continue
        next_start = int(starts.iloc[index + 1])
        page_ends.append(max(next_start - 1, int(start_value)))

    df["page_end"] = pd.Series(page_ends, dtype="Int64")
    return df


def apply_consensus_page_offset(
    toc_df: pd.DataFrame,
    page_texts: list[str],
    *,
    min_similarity: float = 0.72,
) -> pd.DataFrame:
    """Shift printed TOC page numbers to physical PDF pages using title matches."""
    if toc_df.empty or not page_texts or "text" not in toc_df.columns or "page_num" not in toc_df.columns:
        return toc_df.copy()

    df = toc_df.copy()
    df["displayed_page"] = pd.to_numeric(df["page_num"], errors="coerce").astype("Int64")

    offsets: list[int] = []
    for row in df.itertuples(index=False):
        if pd.isna(row.displayed_page):
            continue
        actual_page, similarity = _find_best_matching_page(str(row.text), page_texts)
        if actual_page is None or similarity < min_similarity:
            continue
        offsets.append(int(actual_page) - int(row.displayed_page))

    offset = Counter(offsets).most_common(1)[0][0] if offsets else 0
    max_page = len(page_texts)

    def _shift_page(page_value: object) -> int | None:
        if pd.isna(page_value):
            return None
        shifted = int(page_value) + offset
        return min(max(shifted, 1), max_page)

    df["page_num"] = df["displayed_page"].map(_shift_page).astype("Int64")
    df["page_offset"] = offset
    return df


def _find_best_matching_page(title: str, page_texts: list[str]) -> tuple[int | None, float]:
    normalised_title = normalize_text(title)
    if len(normalised_title) < 4:
        return None, 0.0

    best_page: int | None = None
    best_score = 0.0
    for page_number, page_text in enumerate(page_texts, start=1):
        candidate_score = _best_title_match_score(normalised_title, page_text)
        if candidate_score > best_score:
            best_page = page_number
            best_score = candidate_score

    return best_page, best_score


def _best_title_match_score(normalised_title: str, page_text: str) -> float:
    best_score = 0.0
    for raw_line in str(page_text).splitlines():
        normalised_line = normalize_text(raw_line)
        if not normalised_line:
            continue
        if normalised_title == normalised_line:
            return 1.0
        if normalised_title in normalised_line or normalised_line in normalised_title:
            best_score = max(best_score, 0.92)
            continue
        best_score = max(best_score, SequenceMatcher(None, normalised_title, normalised_line).ratio())
    return best_score
"""Internal helpers for TOC dataframe normalisation."""

from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher

import pandas as pd

from .reader import normalize_text

_SECTION_PREFIX_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)[.)]?\s+")
_SECTION_ONLY_RE = re.compile(r"^\s*\d+(?:\.\d+)*[.)]?\s*$")
TARGET_TOC_COLUMNS: list[str] = [
    "text",
    "level",
    "indicator",
    "page_num_displayed",
    "page_num_real",
    "page_end",
    "source_page",
    "source",
    "validated",
]
VALID_SOURCES: set[str] = {"native", "links", "dotted", "multiline", "numbering", "style"}


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
    """Compat: convert legacy ``page_num`` (displayed) into physical pages.

    Cette fonction conserve le contrat historique en gardant ``page_num`` comme
    numéro physique 1-base en sortie, et expose aussi ``displayed_page``.
    """
    if toc_df.empty or "page_num" not in toc_df.columns:
        return toc_df.copy()

    df = toc_df.rename(columns={"page_num": "page_num_displayed"}).copy()
    df = compute_page_offset(df, page_texts, min_similarity=min_similarity)
    df["page_num"] = df["page_num_real"]
    df["displayed_page"] = df["page_num_displayed"]
    return df


def compute_page_offset(
    toc_df: pd.DataFrame,
    page_texts: list[str],
    *,
    min_similarity: float = 0.72,
) -> pd.DataFrame:
    """Calculer ``page_num_real`` (1-base) depuis ``page_num_displayed``.

    Args:
        toc_df: DataFrame contenant au minimum ``text`` et
            ``page_num_displayed``.
        page_texts: Texte de chaque page physique du PDF (index 1-base logique).
        min_similarity: Seuil de similarité pour considérer un appariement
            titre/page comme valide.

    Returns:
        DataFrame enrichi avec ``page_num_real``, ``page_offset`` et
        ``validated`` (True si un offset consensus a pu être confirmé).
    """
    required_columns = {"text", "page_num_displayed"}
    if toc_df.empty or not page_texts or not required_columns.issubset(toc_df.columns):
        return toc_df.copy()

    df = toc_df.copy()
    df["page_num_displayed"] = pd.to_numeric(df["page_num_displayed"], errors="coerce").astype("Int64")

    offsets: list[int] = []
    for row in df.itertuples(index=False):
        displayed_page = getattr(row, "page_num_displayed", pd.NA)
        if pd.isna(displayed_page):
            continue
        actual_page, similarity = _find_best_matching_page(str(row.text), page_texts)
        if actual_page is None or similarity < min_similarity:
            continue
        offsets.append(int(actual_page) - int(displayed_page))

    offset = Counter(offsets).most_common(1)[0][0] if offsets else 0
    has_valid_offset = bool(offsets)
    max_page = len(page_texts)

    def _shift_page(page_value: object) -> int | None:
        if pd.isna(page_value):
            return None
        shifted = int(page_value) + offset
        return min(max(shifted, 1), max_page)

    df["page_num_real"] = df["page_num_displayed"].map(_shift_page).astype("Int64")
    df["page_offset"] = offset
    df["validated"] = has_valid_offset
    return df


def normalize_toc_schema(
    toc_df: pd.DataFrame,
    *,
    source: str,
    validated_default: bool = False,
) -> pd.DataFrame:
    """Normalize a TOC dataframe to the canonical package schema.

    Args:
        toc_df: Strategy-specific TOC dataframe.
        source: One of ``native``, ``links``, ``dotted``, ``multiline``,
            ``numbering``, ``style``.
        validated_default: Default validation flag when not already present.

    Returns:
        DataFrame with canonical columns and dtypes.
    """
    if source not in VALID_SOURCES:
        raise ValueError(f"Invalid TOC source '{source}'. Expected one of {sorted(VALID_SOURCES)}")

    df = toc_df.copy()
    if "title" in df.columns and "text" not in df.columns:
        df = df.rename(columns={"title": "text"})

    if "text" not in df.columns:
        df["text"] = pd.Series(dtype="object")

    df["text"] = df["text"].astype(str).str.strip()
    if not df.empty:
        df = df[df["text"] != ""].copy()

    if "page_num_real" not in df.columns:
        if "page" in df.columns:
            df["page_num_real"] = df["page"]
        elif "page_num" in df.columns:
            df["page_num_real"] = df["page_num"]
        elif "page_num_displayed" in df.columns:
            df["page_num_real"] = df["page_num_displayed"]

    if "page_num_displayed" not in df.columns:
        df["page_num_displayed"] = pd.Series(pd.NA, index=df.index, dtype="Int64")

    if "source_page" not in df.columns:
        df["source_page"] = pd.Series(pd.NA, index=df.index, dtype="Int64")

    df = add_toc_metadata(df)

    df["page_num_real"] = pd.to_numeric(df.get("page_num_real"), errors="coerce")
    if not df.empty:
        df = df[df["page_num_real"].notna()].copy()
    df["page_num_real"] = df["page_num_real"].astype("int64")
    if not df.empty:
        df = df[df["page_num_real"] >= 1].copy()

    df["page_num_displayed"] = pd.to_numeric(df["page_num_displayed"], errors="coerce").astype("Int64")
    df["source_page"] = pd.to_numeric(df["source_page"], errors="coerce").astype("Int64")

    df = df.sort_values(["page_num_real", "level", "text"], kind="stable").reset_index(drop=True)
    df = add_page_end_column(df, page_column="page_num_real")

    if "validated" in df.columns:
        df["validated"] = df["validated"].fillna(validated_default).astype(bool)
    else:
        df["validated"] = bool(validated_default)

    df["source"] = source
    df["level"] = pd.to_numeric(df["level"], errors="coerce").fillna(1).astype("int64")
    df["indicator"] = df["indicator"].astype(str)
    df["text"] = df["text"].astype(str)
    df["page_end"] = pd.to_numeric(df["page_end"], errors="coerce").astype("Int64")

    normalized = df.reindex(columns=TARGET_TOC_COLUMNS).copy()
    normalized["page_num"] = normalized["page_num_real"]
    normalized["title"] = normalized["text"]
    normalized["page"] = normalized["page_num_real"]
    return normalized


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
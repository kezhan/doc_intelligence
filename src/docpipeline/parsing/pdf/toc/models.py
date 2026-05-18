"""Data models for PDF TOC detection."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field

pd = importlib.import_module("pandas")

SOURCE_NATIVE = "native"
SOURCE_LINKS = "links"
SOURCE_DOTTED = "dotted"
SOURCE_MULTILINE = "multiline"
SOURCE_NUMBERING = "numbering"
SOURCE_STYLE = "style"

VALID_TOC_SOURCES: tuple[str, ...] = (
    SOURCE_NATIVE,
    SOURCE_LINKS,
    SOURCE_DOTTED,
    SOURCE_MULTILINE,
    SOURCE_NUMBERING,
    SOURCE_STYLE,
)

_CANONICAL_TOC_COLUMNS: tuple[str, ...] = (
    "text",
    "level",
    "indicator",
    "page_num_displayed",
    "page_num_real",
    "page_end",
    "source_page",
    "source",
    "validated",
)

_COMPATIBILITY_COLUMNS: tuple[str, ...] = ("page_num", "title", "page")


@dataclass
class PageAnalysis:
    """Analysis result for a single PDF page."""

    page_number: int
    text: str
    score: float
    signals: list[str] = field(default_factory=list)


@dataclass
class TocDetectionResult:
    """Result returned by :func:`docpipeline.parsing.pdf.toc.detect_toc`."""

    has_toc: bool
    confidence: float
    toc_pages: list[int]
    reason: str

    def to_dict(self) -> dict[str, bool | float | list[int] | str]:
        """Serialise the result to a plain dictionary."""
        return {
            "has_toc": self.has_toc,
            "confidence": round(self.confidence, 4),
            "toc_pages": self.toc_pages,
            "reason": self.reason,
        }


def empty_toc_df():
    """Return an empty TOC dataframe matching the canonical schema.

    Returns:
        Empty pandas DataFrame with canonical TOC columns plus compatibility
        aliases for legacy consumers.
    """
    return pd.DataFrame(
        {
            "text": pd.Series(dtype="object"),
            "level": pd.Series(dtype="int64"),
            "indicator": pd.Series(dtype="object"),
            "page_num_displayed": pd.Series(dtype="Int64"),
            "page_num_real": pd.Series(dtype="int64"),
            "page_end": pd.Series(dtype="Int64"),
            "source_page": pd.Series(dtype="Int64"),
            "source": pd.Series(dtype="object"),
            "validated": pd.Series(dtype="bool"),
            "page_num": pd.Series(dtype="Int64"),
            "title": pd.Series(dtype="object"),
            "page": pd.Series(dtype="Int64"),
        }
    )


def validate_toc_df(df) -> bool:
    """Validate that a TOC dataframe matches the expected schema.

    Args:
        df: Dataframe to validate.

    Returns:
        True when the dataframe has the required columns and dtypes.

    Raises:
        ValueError: If a required column is missing or has an invalid dtype.
    """

    def _fail(message: str) -> None:
        raise ValueError(f"Invalid TOC dataframe: {message}")

    required_columns = [
        "text",
        "level",
        "indicator",
        "page_num_real",
        "source",
        "validated",
    ]
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        _fail(f"missing required columns: {', '.join(missing_columns)}")

    if not pd.api.types.is_object_dtype(df["text"]):
        _fail("column 'text' must use object/string dtype")
    if not pd.api.types.is_integer_dtype(df["level"]):
        _fail("column 'level' must be integer dtype")
    if not pd.api.types.is_object_dtype(df["indicator"]):
        _fail("column 'indicator' must use object/string dtype")
    if not pd.api.types.is_integer_dtype(df["page_num_real"]):
        _fail("column 'page_num_real' must be integer dtype")
    if df["page_num_real"].isna().any():
        _fail("column 'page_num_real' must not contain null values")

    if "page_num_displayed" in df.columns and not pd.api.types.is_integer_dtype(df["page_num_displayed"]):
        _fail("column 'page_num_displayed' must be nullable integer dtype")
    if "page_end" in df.columns and not pd.api.types.is_integer_dtype(df["page_end"]):
        _fail("column 'page_end' must be nullable integer dtype")
    if "source_page" in df.columns and not pd.api.types.is_integer_dtype(df["source_page"]):
        _fail("column 'source_page' must be nullable integer dtype")

    if not pd.api.types.is_object_dtype(df["source"]):
        _fail("column 'source' must use object/string dtype")
    invalid_sources = set(df["source"].dropna().astype(str)) - set(VALID_TOC_SOURCES)
    if invalid_sources:
        _fail(f"column 'source' contains invalid values: {', '.join(sorted(invalid_sources))}")

    if not pd.api.types.is_bool_dtype(df["validated"]):
        _fail("column 'validated' must be boolean dtype")

    return True


__all__ = [
    "SOURCE_NATIVE",
    "SOURCE_LINKS",
    "SOURCE_DOTTED",
    "SOURCE_MULTILINE",
    "SOURCE_NUMBERING",
    "SOURCE_STYLE",
    "VALID_TOC_SOURCES",
    "empty_toc_df",
    "validate_toc_df",
    "PageAnalysis",
    "TocDetectionResult",
]

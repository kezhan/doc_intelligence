"""Tests for the integrated PDF TOC detection package."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from docpipeline.parsing.pdf.toc import (
    PDFReadError,
    TocDetectionResult,
    clean_toc_df,
    detect_toc,
    find_dotted_leader_lines,
    group_numbered_titles,
    has_toc_keyword,
    score_page,
)


_TOC_PAGE_TEXT = (
    "Sommaire\n"
    "1. Introduction .......... 3\n"
    "2. Architecture .......... 7\n"
    "3. Conclusion ............ 42\n"
)

_PLAIN_PAGE_TEXT = (
    "This chapter describes the system architecture in detail.\n"
    "Security and maintainability are discussed in prose paragraphs.\n"
)


def _make_pages(*texts: str) -> list[dict[str, int | str]]:
    return [{"page_number": index + 1, "text": text} for index, text in enumerate(texts)]


def test_patterns_detect_toc_keywords_and_dotted_leaders() -> None:
    assert has_toc_keyword("TABLE DES MATIÈRES") is True
    assert has_toc_keyword("Architecture and implementation details") is False
    assert len(find_dotted_leader_lines(_TOC_PAGE_TEXT)) == 3


def test_score_page_combines_toc_signals() -> None:
    score, signals = score_page(_TOC_PAGE_TEXT)

    assert score >= 0.5
    assert any("keyword" in signal.lower() for signal in signals)
    assert any("dotted" in signal.lower() for signal in signals)


def test_detect_toc_uses_reader_and_returns_docpipeline_model() -> None:
    with patch(
        "docpipeline.parsing.pdf.toc.detector.extract_text_from_first_pages",
        return_value=_make_pages(_PLAIN_PAGE_TEXT, _TOC_PAGE_TEXT),
    ):
        result = detect_toc("dummy.pdf", threshold=0.5)

    assert isinstance(result, TocDetectionResult)
    assert result.has_toc is True
    assert result.toc_pages == [2]
    assert result.to_dict()["confidence"] >= 0.5


def test_detect_toc_propagates_reader_errors(tmp_path) -> None:
    missing_pdf = tmp_path / "missing.pdf"

    with pytest.raises(PDFReadError, match="missing.pdf"):
        detect_toc(missing_pdf)


def test_clean_toc_df_drops_invalid_bookmarks_and_adds_indicator() -> None:
    raw = pd.DataFrame(
        [
            {"level": 1, "title": "Intro", "page": 1},
            {"level": 2, "title": "", "page": 2},
            {"level": 1, "title": "Broken", "page": -1},
        ]
    )

    cleaned = clean_toc_df(raw)

    assert cleaned[["level", "title", "page", "indicator"]].to_dict("records") == [
        {"level": 1, "title": "Intro", "page": 1, "indicator": "L1"}
    ]


def test_group_numbered_titles_merges_isolated_section_numbers() -> None:
    raw = pd.DataFrame(
        [
            {"page_num": 3, "line_num": 1, "text": "1."},
            {"page_num": 3, "line_num": 2, "text": "Introduction"},
            {"page_num": 4, "line_num": 1, "text": "Appendix"},
        ]
    )

    grouped = group_numbered_titles(raw)

    assert grouped["text"].tolist() == ["1. Introduction", "Appendix"]

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
    normalize_text,
    score_page,
)
from docpipeline.parsing.pdf.toc._utils import (
    add_toc_metadata,
    apply_consensus_page_offset,
    compute_page_offset,
)
from docpipeline.parsing.pdf.toc.bookmarks import _normalise_bookmark_dataframe


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


def test_detect_toc_scans_full_document_by_default() -> None:
    late_toc_pages = _make_pages(
        _PLAIN_PAGE_TEXT,
        _PLAIN_PAGE_TEXT,
        _PLAIN_PAGE_TEXT,
        _PLAIN_PAGE_TEXT,
        _PLAIN_PAGE_TEXT,
        _TOC_PAGE_TEXT,
    )

    with patch(
        "docpipeline.parsing.pdf.toc.detector.extract_text_from_first_pages",
        return_value=late_toc_pages,
    ) as extract_mock:
        result = detect_toc("dummy.pdf", threshold=0.5)

    assert result.has_toc is True
    assert result.toc_pages == [6]
    extract_mock.assert_called_once_with("dummy.pdf", max_pages=None)


def test_detect_toc_propagates_reader_errors(tmp_path) -> None:
    missing_pdf = tmp_path / "missing.pdf"

    with pytest.raises(PDFReadError, match="missing.pdf"):
        detect_toc(missing_pdf)


def test_clean_toc_df_drops_invalid_bookmarks_and_adds_indicator() -> None:
    raw = pd.DataFrame(
        [
            {"level": 1, "title": "Intro", "page": 1},
            {"level": 2, "title": "", "page": 2},
            {"level": 2, "title": "Zero", "page": 0},
            {"level": 1, "title": "Broken", "page": -1},
        ]
    )

    cleaned = clean_toc_df(raw)

    assert cleaned[["level", "title", "page", "page_end", "indicator"]].to_dict("records") == [
        {"level": 1, "title": "Intro", "page": 1, "page_end": None, "indicator": "L1"}
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


def test_add_toc_metadata_infers_level_and_indicator() -> None:
    raw = pd.DataFrame(
        [
            {"text": "1. Introduction", "page_num": 3},
            {"text": "1.1 Scope", "page_num": 4},
            {"text": "Appendix", "page_num": 20},
        ]
    )

    enriched = add_toc_metadata(raw)

    assert enriched[["level", "indicator"]].to_dict("records") == [
        {"level": 1, "indicator": "L1"},
        {"level": 2, "indicator": "L1.1"},
        {"level": 1, "indicator": "L2"},
    ]


def test_apply_consensus_page_offset_maps_printed_to_physical_pages() -> None:
    toc_df = pd.DataFrame(
        [
            {"text": "Introduction", "page_num": 1},
            {"text": "Architecture", "page_num": 5},
        ]
    )
    page_texts = [
        "Cover",
        "Table des matieres",
        "Introduction\nOverview",
        "Body",
        "Body",
        "Architecture\nDeep dive",
    ]

    resolved = apply_consensus_page_offset(toc_df, page_texts)

    assert resolved[["displayed_page", "page_num", "page_offset"]].to_dict("records") == [
        {"displayed_page": 1, "page_num": 3, "page_offset": 2},
        {"displayed_page": 5, "page_num": 6, "page_offset": 2},
    ]


def test_compute_page_offset_uses_explicit_displayed_column() -> None:
    toc_df = pd.DataFrame(
        [
            {"text": "Introduction", "page_num_displayed": 1},
            {"text": "Architecture", "page_num_displayed": 5},
        ]
    )
    page_texts = [
        "Cover",
        "Table des matieres",
        "Introduction\nOverview",
        "Body",
        "Body",
        "Architecture\nDeep dive",
    ]

    resolved = compute_page_offset(toc_df, page_texts)

    assert resolved[["page_num_displayed", "page_num_real", "page_offset"]].to_dict("records") == [
        {"page_num_displayed": 1, "page_num_real": 3, "page_offset": 2},
        {"page_num_displayed": 5, "page_num_real": 6, "page_offset": 2},
    ]


def test_normalise_bookmark_dataframe_accepts_native_schema() -> None:
    native_df = pd.DataFrame([{"title": "Intro", "page": 3, "level": 1}])

    normalised = _normalise_bookmark_dataframe(native_df)

    assert normalised[["text", "page_num", "level"]].to_dict("records") == [
        {"text": "Intro", "page_num": 3, "level": 1}
    ]


def test_normalise_bookmark_dataframe_accepts_page_num_real_schema() -> None:
    real_df = pd.DataFrame([{"text": "Intro", "page_num_real": 3, "level": 1}])

    normalised = _normalise_bookmark_dataframe(real_df)

    assert normalised[["text", "page_num", "level"]].to_dict("records") == [
        {"text": "Intro", "page_num": 3, "level": 1}
    ]


def test_normalize_text_collapses_case_punctuation_and_spacing() -> None:
    assert normalize_text("  Table-des\u00a0mati\u00e8res!  ") == "table des matières"

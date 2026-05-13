"""Tests pour `apply_translation_scope` (Step 4 build order Tome 2)."""

from __future__ import annotations

import warnings
from pathlib import Path

import pandas as pd
import pytest

from docpipeline.translation.scope_js import (
    TranslationScope,
    apply_translation_scope,
)


# -------- Schema TranslationScope --------------------------------------------

def test_scope_default_is_none_everywhere():
    sc = TranslationScope()
    assert sc.page_range is None
    assert sc.include_sections is None
    assert sc.exclude_sections is None


def test_scope_rejects_invalid_page_range():
    with pytest.raises(Exception):
        TranslationScope(page_range=(0, 3))
    with pytest.raises(Exception):
        TranslationScope(page_range=(5, 2))


def test_scope_accepts_valid_page_range():
    sc = TranslationScope(page_range=(1, 5))
    assert sc.page_range == (1, 5)


# -------- Cas trivial : scope None -------------------------------------------

def test_scope_none_returns_all_selected_nothing_skipped():
    line_df = pd.DataFrame({"page_num": [1, 2], "line_num": [0, 0], "text": ["a", "b"]})
    span_df = pd.DataFrame(
        {"page_num": [1, 2], "line_num": [0, 0], "span_id": ["s1", "s2"], "text": ["x", "y"]}
    )
    sl, ss, kl, ks = apply_translation_scope(line_df, span_df, None)
    assert len(sl) == 2 and len(ss) == 2
    assert len(kl) == 0 and len(ks) == 0


# -------- page_range (PDF case) ----------------------------------------------

def test_page_range_pdf_filters_lines_and_spans():
    line_df = pd.DataFrame(
        {"page_num": [1, 1, 2, 3], "line_num": [0, 1, 0, 0], "text": list("abcd")}
    )
    span_df = pd.DataFrame(
        {
            "page_num": [1, 1, 1, 2, 3],
            "line_num": [0, 0, 1, 0, 0],
            "span_id": ["s1", "s2", "s3", "s4", "s5"],
            "text": list("vwxyz"),
        }
    )
    scope = TranslationScope(page_range=(1, 2))
    sl, ss, kl, ks = apply_translation_scope(line_df, span_df, scope)
    assert sorted(sl["page_num"].unique().tolist()) == [1, 2]
    assert sorted(kl["page_num"].unique().tolist()) == [3]
    assert set(ss["span_id"]) == {"s1", "s2", "s3", "s4"}
    assert set(ks["span_id"]) == {"s5"}


def test_page_range_warns_when_no_page_num_column():
    line_df = pd.DataFrame({"paragraph_index": [0, 1], "text": ["a", "b"]})
    span_df = pd.DataFrame(
        {"paragraph_index": [0, 1], "span_id": ["s1", "s2"], "text": ["x", "y"]}
    )
    scope = TranslationScope(page_range=(1, 2))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        sl, ss, kl, ks = apply_translation_scope(line_df, span_df, scope)
    assert any("page_num" in str(w.message) for w in caught)
    assert len(sl) == 2 and len(kl) == 0


# -------- include_sections / exclude_sections --------------------------------

def test_exclude_sections_case_accent_insensitive():
    line_df = pd.DataFrame(
        {
            "page_num": [1, 2, 3],
            "line_num": [0, 0, 0],
            "section_breadcrumb": ["Body", "Annexes", "Conclusion"],
            "text": ["a", "b", "c"],
        }
    )
    span_df = pd.DataFrame(
        {
            "page_num": [1, 2, 3],
            "line_num": [0, 0, 0],
            "span_id": ["s1", "s2", "s3"],
            "text": ["x", "y", "z"],
        }
    )
    # "ANNEXES" en majuscules + accent → doit matcher "Annexes"
    scope = TranslationScope(exclude_sections=["ANNEXÉS"])
    sl, ss, kl, ks = apply_translation_scope(line_df, span_df, scope)
    assert "Annexes" not in sl["section_breadcrumb"].tolist()
    assert kl["section_breadcrumb"].tolist() == ["Annexes"]
    assert ks["span_id"].tolist() == ["s2"]


def test_include_sections_keeps_only_matched():
    line_df = pd.DataFrame(
        {
            "page_num": [1, 2, 3],
            "line_num": [0, 0, 0],
            "section_breadcrumb": ["Body", "Annexes", "Conclusion"],
            "text": ["a", "b", "c"],
        }
    )
    span_df = pd.DataFrame(
        {
            "page_num": [1, 2, 3],
            "line_num": [0, 0, 0],
            "span_id": ["s1", "s2", "s3"],
            "text": ["x", "y", "z"],
        }
    )
    scope = TranslationScope(include_sections=["conclusion"])
    sl, ss, kl, ks = apply_translation_scope(line_df, span_df, scope)
    assert sl["section_breadcrumb"].tolist() == ["Conclusion"]
    assert sorted(kl["section_breadcrumb"].tolist()) == ["Annexes", "Body"]


def test_include_then_exclude_is_intersection():
    line_df = pd.DataFrame(
        {
            "page_num": [1, 2, 3],
            "line_num": [0, 0, 0],
            "section_breadcrumb": [
                "Chapter 1 / Body",
                "Chapter 1 / Annexes",
                "Chapter 2 / Body",
            ],
            "text": ["a", "b", "c"],
        }
    )
    span_df = pd.DataFrame(
        {
            "page_num": [1, 2, 3],
            "line_num": [0, 0, 0],
            "span_id": ["s1", "s2", "s3"],
            "text": ["x", "y", "z"],
        }
    )
    scope = TranslationScope(
        include_sections=["Chapter 1"], exclude_sections=["Annexes"]
    )
    sl, ss, kl, ks = apply_translation_scope(line_df, span_df, scope)
    assert sl["section_breadcrumb"].tolist() == ["Chapter 1 / Body"]


def test_section_filter_warns_when_no_section_breadcrumb():
    line_df = pd.DataFrame({"page_num": [1, 2], "line_num": [0, 0], "text": ["a", "b"]})
    span_df = pd.DataFrame(
        {"page_num": [1, 2], "line_num": [0, 0], "span_id": ["s1", "s2"], "text": ["x", "y"]}
    )
    scope = TranslationScope(exclude_sections=["Annexes"])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        sl, ss, kl, ks = apply_translation_scope(line_df, span_df, scope)
    assert any("section_breadcrumb" in str(w.message) for w in caught)
    assert len(sl) == 2 and len(kl) == 0


# -------- Word integration (paragraph_index FK) ------------------------------

def test_word_paragraph_index_fk_propagates_to_spans():
    """Cas Word : paragraph_df + span_df partagent paragraph_index."""
    line_df = pd.DataFrame(
        {
            "paragraph_index": [0, 1, 2],
            "section_breadcrumb": ["Intro", "Body", "Conclusion"],
            "text": ["t0", "t1", "t2"],
        }
    )
    span_df = pd.DataFrame(
        {
            "paragraph_index": [0, 1, 1, 2],
            "span_id": ["w_0_0", "w_1_0", "w_1_1", "w_2_0"],
            "text": ["a", "b", "c", "d"],
        }
    )
    scope = TranslationScope(exclude_sections=["Body"])
    sl, ss, kl, ks = apply_translation_scope(line_df, span_df, scope)
    assert sorted(sl["paragraph_index"].tolist()) == [0, 2]
    assert set(ss["span_id"]) == {"w_0_0", "w_2_0"}
    assert set(ks["span_id"]) == {"w_1_0", "w_1_1"}


# -------- Vraie fixture Word (contrat_assurance) -----------------------------

FIX = Path(__file__).parent / "fixtures" / "contrat_assurance.docx"


@pytest.mark.skipif(not FIX.exists(), reason="fixture contrat_assurance.docx absente")
def test_word_fixture_scope_none_keeps_all_runs():
    from docpipeline.parsing.word import parse_word

    parsed = parse_word(FIX)
    paragraph_df = parsed["paragraph_df"]
    span_df = parsed["span_df"]

    sl, ss, kl, ks = apply_translation_scope(paragraph_df, span_df, None)
    assert len(sl) == len(paragraph_df)
    assert len(ss) == len(span_df)
    assert len(kl) == 0 and len(ks) == 0


@pytest.mark.skipif(not FIX.exists(), reason="fixture contrat_assurance.docx absente")
def test_word_fixture_table_cells_always_selected_when_filtered_by_paragraph():
    """Bug fix : les cells de tableau ont paragraph_index cell-interne (=0),
    le merge naif les filterait a tort. Convention : cells toujours selected."""
    from docpipeline.parsing.word import parse_word

    parsed = parse_word(FIX)
    paragraph_df = parsed["paragraph_df"].copy()
    span_df = parsed["span_df"]

    # On simule un section_breadcrumb : Body sur para 0-6, Annexes sur 7-9
    paragraph_df["section_breadcrumb"] = "Body"
    paragraph_df.loc[
        paragraph_df["paragraph_index"].isin([7, 8, 9]), "section_breadcrumb"
    ] = "Annexes"

    sc = TranslationScope(exclude_sections=["Annexes"])
    sl, ss, kl, ks = apply_translation_scope(paragraph_df, span_df, sc)

    # Cells toujours dans selected
    n_cells = int(span_df["in_table"].sum())
    assert int(ss["in_table"].sum()) == n_cells
    # Skipped contient uniquement des body spans
    assert (ks["in_table"] == False).all()
    # Body spans des paragraphs Annexes (7,8,9) doivent etre dans skipped
    expected_skipped = span_df[
        (~span_df["in_table"].astype(bool))
        & (span_df["paragraph_index"].isin([7, 8, 9]))
    ]
    assert len(ks) == len(expected_skipped)


# -------- Conservation des types et colonnes ---------------------------------

def test_columns_preserved_on_filtered_outputs():
    line_df = pd.DataFrame(
        {"page_num": [1, 2], "line_num": [0, 0], "text": ["a", "b"], "extra": [10, 20]}
    )
    span_df = pd.DataFrame(
        {"page_num": [1, 2], "line_num": [0, 0], "span_id": ["s1", "s2"], "bold": [True, False]}
    )
    scope = TranslationScope(page_range=(1, 1))
    sl, ss, kl, ks = apply_translation_scope(line_df, span_df, scope)
    assert list(sl.columns) == list(line_df.columns)
    assert list(ss.columns) == list(span_df.columns)
    assert sl["extra"].tolist() == [10]
    assert ss["bold"].tolist() == [True]

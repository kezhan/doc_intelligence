"""Tests pour parse_pdf — script unique d'analyse PDF."""

from __future__ import annotations

from pathlib import Path

import pytest

from docpipeline.parsing.pdf.parse_pdf import (
    CATEGORY_DESIGN_TOOL,
    CATEGORY_OTHER,
    CATEGORY_SCANNED,
    CATEGORY_WORD_NATIVE,
    PAGE_TYPE_EMPTY,
    PAGE_TYPE_MIXED,
    PAGE_TYPE_NATIVE,
    PAGE_TYPE_NATIVE_WITH_IMAGE,
    PAGE_TYPE_SCANNED,
    PAGE_TYPE_SCANNED_OCR_BAD,
    PAGE_TYPE_SCANNED_OCR_GOOD,
    STRATEGY_HYBRID,
    STRATEGY_NATIVE,
    STRATEGY_OCR,
    STRATEGY_SKIP,
    PageInfo,
    PDFInspection,
    _decide_page_type,
    _decide_strategy,
    _detect_tool,
    _normalize,
    _strip_version,
    _text_quality_score,
    classify_inspection,
    inspect_pdf,
    normalize_metadata,
    parse_pdf,
    parse_xmp,
)


CLIENT  = Path(__file__).parent.parent.parent
ALLIANZ = CLIENT / "d_actif_pro_sant2.pdf"
MAAF    = CLIENT / "MAAF_Conditions_generales_Assurance_Tempo_habitation_2339.pdf"


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ Helpers : normalisation, XMP, version                                      ║
# ╚════════════════════════════════════════════════════════════════════════════╝

class TestNormalize:
    def test_lowercase_and_strip(self):
        assert _normalize("  Adobe InDesign  ") == "adobe indesign"

    def test_nbsp_collapsed(self):
        assert _normalize("Acrobat\xa0Distiller") == "acrobat distiller"

    def test_compress_spaces(self):
        assert _normalize("Microsoft   Word") == "microsoft word"

    def test_none_is_empty(self):
        assert _normalize(None) == ""


class TestStripVersion:
    def test_trailing_version(self):
        assert _strip_version("microsoft word 16.0") == "microsoft word"

    def test_trailing_parens(self):
        assert _strip_version("adobe indesign cs5 (7.0)") == "adobe indesign cs5"

    def test_no_version(self):
        assert _strip_version("camscanner") == "camscanner"


class TestParseXmp:
    def test_empty_returns_empty_dict(self):
        assert parse_xmp("") == {}

    def test_history_agents_extracted(self):
        xml = """
        <stEvt:softwareAgent>Adobe InDesign 7.0</stEvt:softwareAgent>
        <stEvt:softwareAgent>Adobe PDF Library</stEvt:softwareAgent>
        """
        out = parse_xmp(xml)
        assert "Adobe InDesign 7.0" in out["history_agents"]


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ Détection d'outil (Adobe InDesign / CamScanner / Microsoft Word / ...)     ║
# ╚════════════════════════════════════════════════════════════════════════════╝

class TestDetectTool:
    def test_microsoft_word(self):
        assert _detect_tool("microsoft word 16.0") == "Microsoft Word"

    def test_adobe_indesign(self):
        assert _detect_tool("adobe indesign cs5") == "Adobe InDesign"

    def test_camscanner(self):
        assert _detect_tool("camscanner 6.32") == "CamScanner"

    def test_libreoffice(self):
        assert _detect_tool("libreoffice 7.4") == "LibreOffice"

    def test_abbyy_finereader(self):
        assert _detect_tool("abbyy finereader 14") == "ABBYY FineReader"

    def test_unknown_returns_none(self):
        assert _detect_tool("totally unknown thing") is None


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ Décision page_type — règles unitaires (sans fitz)                          ║
# ╚════════════════════════════════════════════════════════════════════════════╝

class TestDecidePageType:
    def test_empty_page(self):
        p = PageInfo(page_num=0, char_count=0, n_images=0, drawing_count=0)
        assert _decide_page_type(p) == PAGE_TYPE_EMPTY

    def test_no_fonts_full_image_is_scanned(self):
        p = PageInfo(page_num=0, n_fonts=0, has_full_page_image=True,
                     image_coverage_ratio=0.95, char_count=0,
                     has_image=True, n_images=1)
        assert _decide_page_type(p) == PAGE_TYPE_SCANNED

    def test_full_image_with_good_ocr_layer(self):
        p = PageInfo(page_num=0, n_fonts=2, has_full_page_image=True,
                     image_coverage_ratio=0.92, has_ocr_layer=True,
                     ocr_char_count=500, char_count=500,
                     text_quality_score=0.90)
        assert _decide_page_type(p) == PAGE_TYPE_SCANNED_OCR_GOOD

    def test_full_image_with_bad_ocr_layer(self):
        p = PageInfo(page_num=0, n_fonts=2, has_full_page_image=True,
                     image_coverage_ratio=0.92, has_ocr_layer=True,
                     ocr_char_count=500, char_count=500,
                     text_quality_score=0.40)
        assert _decide_page_type(p) == PAGE_TYPE_SCANNED_OCR_BAD

    def test_mixed_page(self):
        p = PageInfo(page_num=0, n_fonts=2, has_full_page_image=True,
                     image_coverage_ratio=0.90, has_native_text=True,
                     native_char_count=300, char_count=300)
        assert _decide_page_type(p) == PAGE_TYPE_MIXED

    def test_native_with_image(self):
        p = PageInfo(page_num=0, n_fonts=3, has_image=True, n_images=2,
                     has_native_text=True, native_char_count=2000,
                     char_count=2000, image_coverage_ratio=0.20)
        assert _decide_page_type(p) == PAGE_TYPE_NATIVE_WITH_IMAGE

    def test_pure_native(self):
        p = PageInfo(page_num=0, n_fonts=2, has_native_text=True,
                     native_char_count=3000, char_count=3000)
        assert _decide_page_type(p) == PAGE_TYPE_NATIVE


class TestDecideStrategy:
    def test_native_strategy(self):
        assert _decide_strategy(PAGE_TYPE_NATIVE) == STRATEGY_NATIVE
        assert _decide_strategy(PAGE_TYPE_NATIVE_WITH_IMAGE) == STRATEGY_NATIVE
        assert _decide_strategy(PAGE_TYPE_SCANNED_OCR_GOOD) == STRATEGY_NATIVE

    def test_ocr_strategy(self):
        assert _decide_strategy(PAGE_TYPE_SCANNED) == STRATEGY_OCR
        assert _decide_strategy(PAGE_TYPE_SCANNED_OCR_BAD) == STRATEGY_OCR

    def test_hybrid_for_mixed(self):
        assert _decide_strategy(PAGE_TYPE_MIXED) == STRATEGY_HYBRID

    def test_skip_for_empty(self):
        assert _decide_strategy(PAGE_TYPE_EMPTY) == STRATEGY_SKIP


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ Score qualité OCR                                                          ║
# ╚════════════════════════════════════════════════════════════════════════════╝

class TestTextQualityScore:
    def test_clean_text_high_score(self):
        text = "Le contrat d'assurance habitation couvre les biens du souscripteur."
        assert _text_quality_score(text) >= 0.85

    def test_replacement_chars_lower_score(self):
        clean = "Le contrat d'assurance habitation couvre les biens du souscripteur."
        bad   = "L� contr�t d'assur�nce h�bitation cou�re les bi�ns du souscript�ur."
        assert _text_quality_score(bad) < _text_quality_score(clean) - 0.20

    def test_empty_text_zero(self):
        assert _text_quality_score("") == 0.0


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ Intégration — Allianz (mixte InDesign + page CamScanner-like)              ║
# ╚════════════════════════════════════════════════════════════════════════════╝

@pytest.mark.skipif(not ALLIANZ.exists(), reason="Allianz PDF absent")
class TestParsePdfAllianz:
    def test_returns_four_keys(self):
        r = parse_pdf(ALLIANZ)
        assert set(r.keys()) == {"line_df", "image_df", "page_df", "doc_summary"}

    def test_dataframes_have_pdf_hash_pk(self):
        r = parse_pdf(ALLIANZ)
        for name in ("line_df", "image_df", "page_df"):
            assert "pdf_hash" in r[name].columns, f"{name} doit avoir pdf_hash en PK"

    def test_page_df_has_one_row_per_page(self):
        r = parse_pdf(ALLIANZ)
        assert len(r["page_df"]) == 6

    def test_doc_summary_source_is_indesign(self):
        r = parse_pdf(ALLIANZ)
        assert r["doc_summary"]["source_tool"] == "Adobe InDesign"
        assert r["doc_summary"]["source_category"] == CATEGORY_DESIGN_TOOL

    def test_doc_summary_has_recommendation(self):
        r = parse_pdf(ALLIANZ)
        assert r["doc_summary"]["recommended_strategy"] in (
            "per_page_routing", "use_native_extraction", "rerun_ocr",
            "use_existing_ocr", "run_ocr"
        )

    def test_line_df_has_invisible_flag(self):
        r = parse_pdf(ALLIANZ)
        assert "is_invisible" in r["line_df"].columns

    def test_pdf_hash_is_sha256(self):
        r = parse_pdf(ALLIANZ)
        h = r["doc_summary"]["pdf_hash"]
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ Intégration — MAAF (design_tool pur)                                       ║
# ╚════════════════════════════════════════════════════════════════════════════╝

@pytest.mark.skipif(not MAAF.exists(), reason="MAAF PDF absent")
class TestParsePdfMaaf:
    def test_source_tool_is_indesign(self):
        r = parse_pdf(MAAF)
        assert r["doc_summary"]["source_tool"] == "Adobe InDesign"

    def test_no_pages_need_ocr(self):
        r = parse_pdf(MAAF)
        assert r["doc_summary"]["pages_needing_ocr"] == []
        assert r["doc_summary"]["pages_needing_reocr"] == []

    def test_recommended_strategy_is_native(self):
        r = parse_pdf(MAAF)
        assert r["doc_summary"]["recommended_strategy"] == "use_native_extraction"


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ Contrat                                                                    ║
# ╚════════════════════════════════════════════════════════════════════════════╝

@pytest.mark.skipif(not ALLIANZ.exists(), reason="Allianz PDF absent")
class TestPDFInspectionContract:
    def test_inspect_then_classify_is_idempotent(self):
        insp = inspect_pdf(ALLIANZ)
        insp1 = classify_inspection(insp)
        types1 = [p.page_type for p in insp1.pages]
        insp2 = classify_inspection(insp1)
        types2 = [p.page_type for p in insp2.pages]
        assert types1 == types2

    def test_dataframes_can_be_serialized_to_json(self):
        r = parse_pdf(ALLIANZ)
        for name in ("line_df", "image_df", "page_df"):
            r[name].to_json()

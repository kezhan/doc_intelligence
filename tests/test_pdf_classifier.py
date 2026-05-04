"""Tests pour TODO-001 à 004 — classification PDF à 3 niveaux (sans LLM)."""

from unittest.mock import MagicMock, patch

import pytest

from docpipeline.parsing.pdf.classifier import (
    PDFCategory,
    PDFClassification,
    ScannedNoTextResult,
    _is_standard_size,
    _text_quality_score,
    _classify_by_content,
    PageMetrics,
    classify_pdf,
    detect_scanned_no_text,
    detect_native_text,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_page_metrics(
    char_count=500, image_area_ratio=0.05, block_count=8,
    font_names=None, has_full_page_image=False,
    width=595, height=842,
) -> PageMetrics:
    return PageMetrics(
        width=width, height=height,
        char_count=char_count,
        image_count=2,
        image_area_ratio=image_area_ratio,
        block_count=block_count,
        font_names=font_names or ["Arial", "Arial-Bold"],
        has_full_page_image=has_full_page_image,
    )


# ── Tests fonctions utilitaires ───────────────────────────────────────────────

class TestTextQualityScore:
    def test_clean_french_text(self):
        text = "Le contrat d'assurance couvre les accidents individuels survenus."
        assert _text_quality_score(text) >= 0.80

    def test_ocr_garbage(self):
        text = "##@$% ^^[] \\|< ~` @@@##$ %%%"
        assert _text_quality_score(text) < 0.30

    def test_empty_returns_zero(self):
        assert _text_quality_score("") == 0.0


class TestIsStandardSize:
    def test_a4_portrait(self):
        assert _is_standard_size(595, 842) is True

    def test_a4_landscape(self):
        assert _is_standard_size(842, 595) is True

    def test_letter(self):
        assert _is_standard_size(612, 792) is True

    def test_non_standard_poster(self):
        assert _is_standard_size(1200, 1800) is False

    def test_a4_with_slight_variation(self):
        # ±5% de tolérance
        assert _is_standard_size(590, 838) is True


# ── Tests classification par contenu ─────────────────────────────────────────

class TestClassifyByContent:

    def test_scanned_full_page_images(self):
        # Pages avec image plein format et pas de texte → SCANNED
        pages = [
            _make_page_metrics(char_count=10, image_area_ratio=0.92, has_full_page_image=True)
            for _ in range(4)
        ]
        category, confidence, signals = _classify_by_content(pages)
        assert category == PDFCategory.SCANNED
        assert confidence >= 0.80
        assert any("full_page_images" in s for s in signals)

    def test_design_tool_high_image_ratio(self):
        # Beaucoup d'images, peu de blocs texte → DESIGN_TOOL
        pages = [
            _make_page_metrics(char_count=80, image_area_ratio=0.70, block_count=3)
            for _ in range(3)
        ]
        category, confidence, signals = _classify_by_content(pages)
        assert category == PDFCategory.DESIGN_TOOL

    def test_word_native_clean_document(self):
        # Texte dense, taille A4, polices standard → WORD_NATIVE
        pages = [
            _make_page_metrics(
                char_count=800, image_area_ratio=0.05, block_count=10,
                font_names=["Calibri", "Calibri-Bold"], width=595, height=842
            )
            for _ in range(5)
        ]
        category, confidence, signals = _classify_by_content(pages)
        assert category == PDFCategory.WORD_NATIVE
        assert any("standard_page" in s for s in signals)

    def test_empty_pages_returns_other(self):
        category, _, _ = _classify_by_content([])
        assert category == PDFCategory.OTHER


# ── Tests classification complète (N1 métadonnées) ────────────────────────────

class TestClassifyPDFMetadata:

    def _make_doc(self, creator="", producer="", page_count=3, text="Normal text " * 20):
        doc = MagicMock()
        doc.__enter__ = lambda s: s
        doc.__exit__ = MagicMock(return_value=False)
        doc.metadata = {"creator": creator, "producer": producer}
        doc.page_count = page_count

        page = MagicMock()
        page.get_text = MagicMock(return_value=text)
        page.rect = MagicMock(width=595, height=842)

        # get_text("dict") pour _analyze_page
        page.get_text = MagicMock(side_effect=lambda fmt="text", **kw: (
            text if fmt == "text" else {
                "blocks": [{"type": 0, "lines": [
                    {"spans": [{"font": "Calibri", "text": "Hello"}]}
                ]}] * 5
            }
        ))
        page.get_images = MagicMock(return_value=[])
        page.get_image_info = MagicMock(return_value=[])

        doc.__iter__ = MagicMock(return_value=iter([page] * page_count))
        return doc

    @patch("docpipeline.parsing.pdf.classifier.fitz.open")
    def test_word_native_via_metadata(self, mock_open):
        mock_open.return_value = self._make_doc(creator="Microsoft Word")
        result = classify_pdf("fake.pdf")
        assert result.category == PDFCategory.WORD_NATIVE
        assert result.confidence >= 0.90
        assert "meta:word_creator" in result.signals

    @patch("docpipeline.parsing.pdf.classifier.fitz.open")
    def test_design_tool_via_metadata(self, mock_open):
        mock_open.return_value = self._make_doc(creator="Adobe Photoshop")
        result = classify_pdf("fake.pdf")
        assert result.category == PDFCategory.DESIGN_TOOL
        assert "meta:design_creator" in result.signals

    @patch("docpipeline.parsing.pdf.classifier.fitz.open")
    def test_scanner_via_metadata(self, mock_open):
        mock_open.return_value = self._make_doc(creator="HP ScanJet 3800")
        result = classify_pdf("fake.pdf")
        assert result.category == PDFCategory.SCANNED
        assert "meta:scanner_creator" in result.signals

    @patch("docpipeline.parsing.pdf.classifier.fitz.open")
    def test_result_has_confidence_and_signals(self, mock_open):
        mock_open.return_value = self._make_doc(creator="Microsoft Word")
        result = classify_pdf("fake.pdf")
        assert isinstance(result.confidence, float)
        assert 0.0 <= result.confidence <= 1.0
        assert isinstance(result.signals, list)
        assert len(result.signals) > 0


# ── Tests scanned no text ─────────────────────────────────────────────────────

class TestScannedNoText:

    @patch("docpipeline.parsing.pdf.classifier.fitz.open")
    def test_all_image_pages(self, mock_open):
        doc = MagicMock()
        doc.__enter__ = lambda s: s
        doc.__exit__ = MagicMock(return_value=False)
        page = MagicMock()
        page.get_text = MagicMock(return_value="  ")
        doc.__iter__ = MagicMock(return_value=iter([page, page, page]))
        mock_open.return_value = doc

        result = detect_scanned_no_text("fake.pdf")
        assert result.is_scanned_no_text is True
        assert result.text_page_count == 0
        assert result.text_image_ratio == 0.0

    @patch("docpipeline.parsing.pdf.classifier.fitz.open")
    def test_text_pages_not_scanned(self, mock_open):
        doc = MagicMock()
        doc.__enter__ = lambda s: s
        doc.__exit__ = MagicMock(return_value=False)
        page = MagicMock()
        page.get_text = MagicMock(return_value="Le contrat d'assurance couvre " * 5)
        doc.__iter__ = MagicMock(return_value=iter([page, page]))
        mock_open.return_value = doc

        result = detect_scanned_no_text("fake.pdf")
        assert result.is_scanned_no_text is False
        assert result.text_image_ratio == 1.0

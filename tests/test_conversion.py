"""Tests pour les convertisseurs PDF→Word portés depuis pdf2word."""

from pathlib import Path

import pytest

from docpipeline.conversion import (
    ConversionResult,
    DocxEnhancer,
    SmartConverter,
    TextConverter,
    convert_pdf_to_word,
)
from docpipeline.conversion._smart_converter import SmartConverter as SC
from docpipeline.parsing.pdf.classifier import PDFCategory


FIXTURES = Path(__file__).parent / "fixtures"
PDF_FILE = FIXTURES / "notice_garanties.pdf"


@pytest.fixture(autouse=True)
def _skip_if_no_fixture():
    if not PDF_FILE.exists():
        pytest.skip(f"Fixture absente : {PDF_FILE}")


class TestSmartConverterUtils:
    def test_clean_font_name_strips_subset_prefix(self):
        assert SC._clean_font_name("ABCDEF+Arial") == "Arial"

    def test_clean_font_name_maps_helvetica_to_arial(self):
        assert SC._clean_font_name("Helvetica") == "Arial"

    def test_clean_font_name_strips_style_suffix(self):
        assert SC._clean_font_name("Arial-Bold") == "Arial"

    def test_clean_font_name_empty_returns_empty(self):
        assert SC._clean_font_name("") == ""

    def test_sanitize_strips_control_chars(self):
        assert SC._sanitize("hello\x00world\x07") == "helloworld"

    def test_rgb_to_hex_white(self):
        assert SC._rgb_to_hex((1.0, 1.0, 1.0)) == "FFFFFF"

    def test_rgb_to_hex_black(self):
        assert SC._rgb_to_hex((0.0, 0.0, 0.0)) == "000000"


class TestSmartConverter:
    def test_convert_real_pdf_produces_docx(self, tmp_path):
        out = tmp_path / "out.docx"
        result = SmartConverter().convert(PDF_FILE, out)
        assert Path(result).exists()
        assert out.stat().st_size > 1000


class TestTextConverter:
    def test_convert_real_pdf_produces_docx(self, tmp_path):
        out = tmp_path / "out.docx"
        result = TextConverter().convert(PDF_FILE, out)
        assert Path(result).exists()
        assert out.stat().st_size > 1000


class TestConvertPdfToWord:
    def test_full_pipeline_returns_result(self, tmp_path):
        out = tmp_path / "out.docx"
        result = convert_pdf_to_word(PDF_FILE, out)
        assert isinstance(result, ConversionResult)
        assert result.output_path == out
        assert out.exists()
        assert isinstance(result.category, PDFCategory)
        assert 0.0 <= result.confidence <= 1.0

    def test_force_smart_engine(self, tmp_path):
        out = tmp_path / "out.docx"
        result = convert_pdf_to_word(PDF_FILE, out, force_engine="smart", enhance=False)
        assert "Smart" in result.engine_used

    def test_enhance_flag_applies_post_processing(self, tmp_path):
        out = tmp_path / "out.docx"
        result = convert_pdf_to_word(PDF_FILE, out, enhance=True)
        assert result.enhanced is True


class TestDocxEnhancer:
    def test_enhance_existing_docx(self, tmp_path):
        # Créer un DOCX d'abord
        docx_path = tmp_path / "src.docx"
        SmartConverter().convert(PDF_FILE, docx_path)

        # Puis l'enhance
        out = tmp_path / "enhanced.docx"
        result = DocxEnhancer().enhance(docx_path, output_path=out)
        assert Path(result) == out
        assert out.exists()

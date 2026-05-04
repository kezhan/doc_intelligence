"""Conversion pipelines — PDF→Word, PDF→Excel.

Code entièrement intégré (pas de dépendance au package pdf2word externe).
Sources personnalisées depuis https://github.com/CHRISTMardochee/pdf2word.
"""

from ._docx_enhancer import DocxEnhancer
from ._hybrid_converter import HybridConverter
from ._ocr_converter import OCRConverter
from ._smart_converter import SmartConverter
from ._text_converter import TextConverter
from .pdf_to_word import ConversionResult, convert_pdf_to_word

__all__ = [
    "convert_pdf_to_word",
    "ConversionResult",
    "SmartConverter",
    "TextConverter",
    "OCRConverter",
    "HybridConverter",
    "DocxEnhancer",
]

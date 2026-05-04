"""
Pipeline PDF → Word — Section 4.2 du document Faseya.

Code 100% intégré dans docpipeline (aucune dépendance au package pdf2word externe).
Sources portées et personnalisées depuis https://github.com/CHRISTMardochee/pdf2word.

Sélection automatique du moteur selon la classification PDF :
  word_native  → TextConverter   (pdf2docx, fidélité texte natif)
  design_tool  → SmartConverter  (PyMuPDF, layout complexe)
  scanned      → OCRConverter    (Tesseract/PaddleOCR)
  other        → SmartConverter  (par défaut, le plus robuste)

Aucun LLM n'intervient dans cette brique.
Post-traitement optionnel via DocxEnhancer (11 étapes de nettoyage).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from ..parsing.pdf.classifier import PDFCategory, classify_pdf
from ._docx_enhancer import DocxEnhancer
from ._ocr_converter import OCRConverter
from ._smart_converter import SmartConverter
from ._text_converter import TextConverter

logger = logging.getLogger(__name__)


@dataclass
class ConversionResult:
    output_path: Path
    engine_used: str
    category:    PDFCategory
    confidence:  float
    enhanced:    bool = False
    warnings:    list[str] = field(default_factory=list)


def convert_pdf_to_word(
    pdf_path:    str | Path,
    output_path: str | Path | None = None,
    *,
    enhance:     bool = True,
    force_engine: str | None = None,
    ocr_lang:    str = "fra+eng",
    ocr_engine:  str = "tesseract",
) -> ConversionResult:
    """
    Convertir un PDF en Word avec sélection automatique du moteur.

    Args:
        pdf_path     : chemin du PDF source
        output_path  : chemin .docx de sortie (par défaut, suffixe remplacé)
        enhance      : appliquer le post-traitement DocxEnhancer (11 étapes)
        force_engine : forcer "smart", "text" ou "ocr" (sinon auto)
        ocr_lang     : langues OCR (ex. "fra+eng", "eng")
        ocr_engine   : "tesseract" ou "paddleocr"

    Returns:
        ConversionResult avec chemin de sortie + métadonnées
    """
    pdf_path = Path(pdf_path)
    if output_path is None:
        output_path = pdf_path.with_suffix(".docx")
    else:
        output_path = Path(output_path)

    classification = classify_pdf(pdf_path)
    warnings: list[str] = []

    # Sélection du moteur
    engine_name = force_engine or _select_engine(classification.category)

    if classification.category == PDFCategory.SCANNED and engine_name != "ocr":
        warnings.append(
            "PDF scanné détecté mais moteur OCR non sélectionné — "
            "le résultat risque d'être vide. Utilisez force_engine='ocr'."
        )

    # Exécution
    engine_label = _run_engine(
        engine_name, pdf_path, output_path,
        ocr_lang=ocr_lang, ocr_engine=ocr_engine,
    )

    # Post-traitement
    enhanced = False
    if enhance:
        try:
            DocxEnhancer().enhance(output_path, source_pdf_path=pdf_path)
            enhanced = True
        except Exception as exc:
            warnings.append(f"Enhancement échoué (non-bloquant) : {exc}")
            logger.warning("DocxEnhancer échoué : %s", exc)

    return ConversionResult(
        output_path = output_path,
        engine_used = engine_label,
        category    = classification.category,
        confidence  = classification.confidence,
        enhanced    = enhanced,
        warnings    = warnings,
    )


# ── Sélection moteur ─────────────────────────────────────────────────────────

def _select_engine(category: PDFCategory) -> str:
    return {
        PDFCategory.WORD_NATIVE: "text",
        PDFCategory.DESIGN_TOOL: "smart",
        PDFCategory.SCANNED:     "ocr",
        PDFCategory.OTHER:       "smart",
    }.get(category, "smart")


def _run_engine(
    engine: str,
    pdf_path: Path,
    output_path: Path,
    *,
    ocr_lang: str,
    ocr_engine: str,
) -> str:
    if engine == "text":
        try:
            TextConverter().convert(pdf_path, output_path)
            return "TextConverter (pdf2docx)"
        except Exception as exc:
            logger.warning("TextConverter échoué (%s) → fallback Smart", exc)
            SmartConverter().convert(pdf_path, output_path)
            return "SmartConverter (fallback PyMuPDF)"

    if engine == "ocr":
        OCRConverter(engine=ocr_engine, lang=ocr_lang).convert(pdf_path, output_path)
        return f"OCRConverter ({ocr_engine})"

    SmartConverter().convert(pdf_path, output_path)
    return "SmartConverter (PyMuPDF)"

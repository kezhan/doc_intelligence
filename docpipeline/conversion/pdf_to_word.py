"""
Pipeline PDF → Word — Section 4.2 du document Faseya.

Code 100% intégré dans docpipeline (aucune dépendance au package pdf2word externe).
Sources portées et personnalisées depuis https://github.com/CHRISTMardochee/pdf2word.

Sélection automatique du moteur selon la classification ET la complexité du PDF :
  word_native              → TextConverter   (pdf2docx, fidélité texte natif)
  design_tool simple       → SmartConverter  (PyMuPDF, layout reconstruit)
  design_tool complexe     → HybridConverter (image + texte invisible — fidélité 100%)
  scanned                  → OCRConverter    (Tesseract/PaddleOCR)
  other                    → SmartConverter  (par défaut, le plus robuste)

Heuristique de complexité : un PDF design avec beaucoup d'images plein cadre
(brochure, magazine, plaquette InDesign) → mode hybride pour préserver
strictement le visuel, plutôt que de tenter une reconstruction qui casserait.

Aucun LLM n'intervient dans cette brique.
Post-traitement optionnel via DocxEnhancer (11 étapes de nettoyage).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF

from ..parsing.pdf.classifier import PDFCategory, classify_pdf
from ._docx_enhancer import DocxEnhancer
from ._hybrid_converter import HybridConverter
from ._ocr_converter import OCRConverter
from ._smart_converter import SmartConverter
from ._text_converter import TextConverter

logger = logging.getLogger(__name__)

# Seuil au-dessus duquel un PDF design est considéré "complexe"
# (= au moins une page couverte à >50% par des images)
_COMPLEX_DESIGN_IMAGE_RATIO = 0.50


@dataclass
class ConversionResult:
    output_path: Path
    engine_used: str
    category:    PDFCategory
    confidence:  float
    enhanced:    bool = False
    warnings:    list[str] = field(default_factory=list)


def convert_pdf_to_word(
    pdf_path:     str | Path,
    output_path:  str | Path | None = None,
    *,
    enhance:      bool = True,
    force_engine: str | None = None,
    ocr_lang:     str = "fra+eng",
    ocr_engine:   str = "tesseract",
    hybrid_dpi:   int = 200,
) -> ConversionResult:
    """
    Convertir un PDF en Word avec sélection automatique du moteur.

    Args:
        pdf_path     : chemin du PDF source
        output_path  : chemin .docx de sortie (par défaut, suffixe remplacé)
        enhance      : appliquer le post-traitement DocxEnhancer (11 étapes)
        force_engine : forcer "smart", "text", "ocr" ou "hybrid" (sinon auto)
        ocr_lang     : langues OCR (ex. "fra+eng", "eng")
        ocr_engine   : "tesseract" ou "paddleocr"
        hybrid_dpi   : résolution rendu pour le mode hybride (défaut 200)

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

    # Sélection du moteur — affinée par analyse de complexité pour design_tool
    if force_engine:
        engine_name = force_engine
    else:
        engine_name = _select_engine(pdf_path, classification.category, warnings)

    if classification.category == PDFCategory.SCANNED and engine_name not in ("ocr", "hybrid"):
        warnings.append(
            "PDF scanné détecté : utilisez force_engine='ocr' pour OCR "
            "ou 'hybrid' pour préserver le visuel exact."
        )

    # Exécution
    engine_label = _run_engine(
        engine_name, pdf_path, output_path,
        ocr_lang=ocr_lang, ocr_engine=ocr_engine, hybrid_dpi=hybrid_dpi,
    )

    # Post-traitement (sauf en mode hybride : ça casserait l'image)
    enhanced = False
    if enhance and engine_name != "hybrid":
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

def _select_engine(
    pdf_path: Path,
    category: PDFCategory,
    warnings: list[str],
) -> str:
    """Choix du moteur en fonction de la catégorie ET de la complexité visuelle."""
    if category == PDFCategory.WORD_NATIVE:
        return "text"
    if category == PDFCategory.SCANNED:
        return "ocr"

    # design_tool ou other : décider entre smart (reconstruction) et hybrid (image fidèle)
    if _has_complex_visual_layout(pdf_path):
        warnings.append(
            "Layout visuel complexe détecté (images pleine page) : "
            "moteur hybride sélectionné pour préserver strictement l'apparence."
        )
        return "hybrid"
    return "smart"


def _has_complex_visual_layout(pdf_path: Path) -> bool:
    """
    Détecte un PDF brochure/magazine/plaquette : au moins une page couverte
    à plus de 50% par des images. Pour ce type de PDF, le mode hybride
    (image fidèle) donne un meilleur résultat que la reconstruction Word.
    """
    doc = fitz.open(str(pdf_path))
    try:
        for page in doc:
            page_area = max(page.rect.width * page.rect.height, 1)
            img_area  = sum(
                (b["bbox"][2] - b["bbox"][0]) * (b["bbox"][3] - b["bbox"][1])
                for b in page.get_image_info() if "bbox" in b
            )
            if img_area / page_area >= _COMPLEX_DESIGN_IMAGE_RATIO:
                return True
    finally:
        doc.close()
    return False


def _run_engine(
    engine: str,
    pdf_path: Path,
    output_path: Path,
    *,
    ocr_lang: str,
    ocr_engine: str,
    hybrid_dpi: int,
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

    if engine == "hybrid":
        HybridConverter(dpi=hybrid_dpi).convert(pdf_path, output_path)
        return f"HybridConverter (image+overlay, {hybrid_dpi}dpi)"

    SmartConverter().convert(pdf_path, output_path)
    return "SmartConverter (PyMuPDF)"

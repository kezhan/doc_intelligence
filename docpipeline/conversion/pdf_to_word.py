"""
Pipeline PDF → Word — Section 4.2 du document Faseya.

Code 100% intégré dans docpipeline (aucune dépendance au package pdf2word externe).
Sources portées et personnalisées depuis https://github.com/CHRISTMardochee/pdf2word.

Stratégie : viser à la fois fidélité visuelle ET éditabilité du contenu.
La sélection auto teste les moteurs dans l'ordre suivant pour les PDFs
complexes (design_tool, brochures InDesign...) :

  1. AdobeConverter     — qualité Acrobat Pro (cloud, 500 conv./mois gratuites)
  2. MSWordConverter    — Word PDF Reflow (Windows + Office, gratuit)
  3. LibreOfficeConverter — LibreOffice headless (multi-OS, gratuit)
  4. SmartConverter     — reconstruction PyMuPDF (fallback offline)
  5. HybridConverter    — image + texte invisible (dernier recours, non éditable)

Pour les PDFs simples (word_native), pdf2docx (TextConverter) reste optimal.
Pour les PDFs scannés, OCR (Tesseract/PaddleOCR).

Aucun LLM dans cette brique.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF

from ..parsing.pdf.classifier import PDFCategory, classify_pdf
from ._adobe_converter import AdobeConverter
from ._docling_converter import DoclingConverter
from ._docx_enhancer import DocxEnhancer
from ._hybrid_converter import HybridConverter
from ._libreoffice_converter import LibreOfficeConverter, _find_libreoffice
from ._msword_converter import MSWordConverter
from ._ocr_converter import OCRConverter
from ._overlay_converter import OverlayConverter
from ._smart_converter import SmartConverter
from ._text_converter import TextConverter

logger = logging.getLogger(__name__)

_COMPLEX_DESIGN_IMAGE_RATIO = 0.50


@dataclass
class ConversionResult:
    output_path:   Path
    engine_used:   str
    category:      PDFCategory
    confidence:    float
    enhanced:      bool = False
    editable:      bool = True       # le DOCX permet-il l'édition libre ?
    visual_fidelity: str = "high"    # 'pixel-perfect' | 'high' | 'approximate'
    warnings:      list[str] = field(default_factory=list)


def convert_pdf_to_word(
    pdf_path:     str | Path,
    output_path:  str | Path | None = None,
    *,
    enhance:      bool = True,
    force_engine: str | None = None,
    ocr_lang:     str = "fra+eng",
    ocr_engine:   str = "tesseract",
    hybrid_dpi:   int = 200,
    prefer:       str = "balanced",
) -> ConversionResult:
    """
    Convertir un PDF en Word avec sélection automatique du moteur.

    Args:
        pdf_path     : chemin du PDF source
        output_path  : chemin .docx de sortie
        enhance      : appliquer le post-traitement DocxEnhancer
        force_engine : forcer un moteur ('adobe', 'msword', 'libreoffice',
                       'smart', 'text', 'ocr', 'hybrid')
        ocr_lang     : langues OCR
        ocr_engine   : 'tesseract' ou 'paddleocr'
        hybrid_dpi   : résolution rendu mode hybride
        prefer       : stratégie de sélection :
                       'balanced'  → meilleur compromis fidélité/éditabilité (défaut)
                       'editable'  → privilégie l'édition (jamais hybride)
                       'visual'    → privilégie la fidélité visuelle (hybride si InDesign)

    Returns:
        ConversionResult avec moteur utilisé + indicateurs éditabilité/fidélité
    """
    pdf_path = Path(pdf_path)
    if output_path is None:
        output_path = pdf_path.with_suffix(".docx")
    else:
        output_path = Path(output_path)

    classification = classify_pdf(pdf_path)
    warnings: list[str] = []

    if force_engine:
        engine_name = force_engine
    else:
        engine_name = _select_engine(pdf_path, classification.category, prefer, warnings)

    if classification.category == PDFCategory.SCANNED and engine_name not in ("ocr", "hybrid", "adobe", "docling"):
        warnings.append(
            "PDF scanné détecté : préférez --engine ocr (OCR local) "
            "ou --engine adobe (OCR cloud + édition)."
        )

    engine_label, editable, fidelity = _run_engine(
        engine_name, pdf_path, output_path,
        ocr_lang=ocr_lang, ocr_engine=ocr_engine, hybrid_dpi=hybrid_dpi,
        warnings=warnings,
    )

    enhanced = False
    if enhance and engine_name not in ("hybrid", "adobe", "msword", "libreoffice", "docling"):
        # Adobe/MSWord/LibreOffice/Docling produisent déjà du DOCX propre
        try:
            DocxEnhancer().enhance(output_path, source_pdf_path=pdf_path)
            enhanced = True
        except Exception as exc:
            warnings.append(f"Enhancement échoué (non-bloquant) : {exc}")

    return ConversionResult(
        output_path     = output_path,
        engine_used     = engine_label,
        category        = classification.category,
        confidence      = classification.confidence,
        enhanced        = enhanced,
        editable        = editable,
        visual_fidelity = fidelity,
        warnings        = warnings,
    )


# ── Sélection moteur ─────────────────────────────────────────────────────────

def _select_engine(
    pdf_path: Path,
    category: PDFCategory,
    prefer:   str,
    warnings: list[str],
) -> str:
    """
    Choix du moteur en fonction de :
      - la classification (word_native, design_tool, scanned, other)
      - la complexité visuelle (PDFs InDesign, brochures...)
      - la stratégie demandée (balanced / editable / visual)
      - la disponibilité des moteurs externes (Adobe, MS Word, LibreOffice)
    """
    # PDF Word natif → pdf2docx reste imbattable et rapide
    if category == PDFCategory.WORD_NATIVE:
        return "text"

    # PDF scanné → OCR par défaut
    if category == PDFCategory.SCANNED:
        return "ocr"

    # design_tool ou other : analyser la complexité
    is_complex = _has_complex_visual_layout(pdf_path)

    if not is_complex:
        # PDF moyennement structuré : Smart suffit largement
        return "smart"

    # PDF design complexe (InDesign, brochure...) — viser fidélité ET éditabilité
    # Cascade : Adobe → MSWord → Docling → LibreOffice → fallback selon prefer
    if _adobe_available():
        warnings.append(
            "Layout complexe détecté → moteur Adobe (qualité Acrobat Pro)."
        )
        return "adobe"

    if _msword_available():
        warnings.append(
            "Layout complexe détecté → moteur Microsoft Word (PDF Reflow natif). "
            "Pour une qualité supérieure : configurez ADOBE_CLIENT_ID/SECRET."
        )
        return "msword"

    if _docling_available():
        warnings.append(
            "Layout complexe détecté → moteur Docling (IBM ML, gratuit + offline). "
            "Pour une qualité supérieure : configurez ADOBE_CLIENT_ID/SECRET."
        )
        return "docling"

    if _libreoffice_available():
        warnings.append(
            "Layout complexe détecté → moteur LibreOffice. "
            "Pour une meilleure qualité gratuite : pip install docling"
        )
        return "libreoffice"

    # Aucun moteur premium dispo : choisir selon préférence utilisateur
    if prefer == "visual":
        warnings.append(
            "Layout complexe + aucun moteur premium disponible → mode hybride "
            "(visuel parfait mais texte non éditable). "
            "Pour édition libre : installez LibreOffice ou MS Office."
        )
        return "hybrid"

    # 'balanced' ou 'editable' : préserver l'édition même au prix du layout
    warnings.append(
        "Layout complexe + aucun moteur premium → SmartConverter "
        "(éditable mais layout approximatif). "
        "Recommandé : installez LibreOffice ou configurez Adobe API."
    )
    return "smart"


def _has_complex_visual_layout(pdf_path: Path) -> bool:
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


def _adobe_available() -> bool:
    return bool(os.environ.get("ADOBE_CLIENT_ID") and os.environ.get("ADOBE_CLIENT_SECRET"))


def _msword_available() -> bool:
    import sys
    if sys.platform != "win32":
        return False
    try:
        import win32com.client  # noqa: F401
        return True
    except ImportError:
        return False


def _docling_available() -> bool:
    try:
        import docling  # noqa: F401
        return True
    except ImportError:
        return False


def _libreoffice_available() -> bool:
    return _find_libreoffice() is not None


# ── Exécution moteur ─────────────────────────────────────────────────────────

def _run_engine(
    engine: str,
    pdf_path: Path,
    output_path: Path,
    *,
    ocr_lang: str,
    ocr_engine: str,
    hybrid_dpi: int,
    warnings: list[str],
) -> tuple[str, bool, str]:
    """
    Lance le moteur demandé. Retourne (label, editable, fidelity).
    """
    if engine == "adobe":
        AdobeConverter().convert(pdf_path, output_path)
        return "AdobeConverter (cloud, qualité Acrobat Pro)", True, "pixel-perfect"

    if engine == "msword":
        MSWordConverter().convert(pdf_path, output_path)
        return "MSWordConverter (PDF Reflow natif)", True, "high"

    if engine == "docling":
        DoclingConverter().convert(pdf_path, output_path)
        return "DoclingConverter (IBM ML, offline)", True, "high"

    if engine == "libreoffice":
        LibreOfficeConverter().convert(pdf_path, output_path)
        return "LibreOfficeConverter (headless)", True, "high"

    if engine == "text":
        try:
            TextConverter().convert(pdf_path, output_path)
            return "TextConverter (pdf2docx)", True, "high"
        except Exception as exc:
            logger.warning("TextConverter échoué (%s) → fallback Smart", exc)
            SmartConverter().convert(pdf_path, output_path)
            return "SmartConverter (fallback PyMuPDF)", True, "approximate"

    if engine == "ocr":
        OCRConverter(engine=ocr_engine, lang=ocr_lang).convert(pdf_path, output_path)
        return f"OCRConverter ({ocr_engine})", True, "approximate"

    if engine == "hybrid":
        HybridConverter(dpi=hybrid_dpi).convert(pdf_path, output_path)
        return f"HybridConverter (image+overlay, {hybrid_dpi}dpi)", False, "pixel-perfect"

    if engine == "overlay":
        OverlayConverter(dpi=hybrid_dpi).convert(pdf_path, output_path)
        return f"OverlayConverter (image+textboxes, {hybrid_dpi}dpi)", True, "pixel-perfect"

    SmartConverter().convert(pdf_path, output_path)
    return "SmartConverter (PyMuPDF)", True, "approximate"

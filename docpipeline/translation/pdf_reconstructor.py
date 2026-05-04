"""
TODO-017 — Reconstitution PDF post-traduction.

Crée un nouveau PDF à partir du DataFrame enrichi (texte + style + position)
et des textes traduits, en réutilisant les positions, polices et images
de l'original.

Stratégie : on duplique le PDF source, on efface le texte natif aux positions
des spans, puis on réinscrit le texte traduit dans les mêmes bbox avec les
mêmes attributs de style.

Aucun LLM dans cette brique — pure manipulation PyMuPDF.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class ReconstructionResult:
    output_path:    Path
    spans_replaced: int
    spans_skipped:  int
    warnings:       list[str] = field(default_factory=list)


def reconstruct_pdf_translation(
    source_pdf:        str | Path,
    enriched_df:       pd.DataFrame,
    translated_spans:  dict[str, str],
    output_path:       str | Path,
    *,
    keep_images:       bool = True,
) -> ReconstructionResult:
    """
    TODO-017 — Recomposer un PDF avec les textes traduits.

    Args:
        source_pdf       : PDF original (sert de base graphique)
        enriched_df      : DataFrame retourné par extract_full_with_style()
        translated_spans : dict {span_id: texte_traduit}
        output_path      : chemin du nouveau PDF
        keep_images      : conserver les images embarquées (défaut True)

    Returns:
        ReconstructionResult avec compteurs et avertissements
    """
    source_pdf  = Path(source_pdf)
    output_path = Path(output_path)
    warnings: list[str] = []
    replaced  = 0
    skipped   = 0

    if "span_id" not in enriched_df.columns:
        raise ValueError(
            "Le DataFrame doit provenir de extract_full_with_style() "
            "(colonne 'span_id' requise)."
        )

    doc = fitz.open(str(source_pdf))

    try:
        for _, row in enriched_df.iterrows():
            span_id = row["span_id"]
            if span_id not in translated_spans:
                skipped += 1
                continue

            page_idx = int(row["page"]) - 1
            if page_idx < 0 or page_idx >= len(doc):
                warnings.append(f"Span {span_id} : page {page_idx + 1} hors limites")
                skipped += 1
                continue

            page = doc[page_idx]
            bbox = fitz.Rect(row["x0"], row["y0"], row["x1"], row["y1"])

            # Effacer le texte natif (rectangle blanc) puis réinscrire
            page.add_redact_annot(bbox, fill=(1, 1, 1))
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE if keep_images
                                  else fitz.PDF_REDACT_IMAGE_REMOVE)

            translated = translated_spans[span_id]
            color_hex  = (row.get("color") or "#000000").lstrip("#")
            r, g, b    = _hex_to_rgb_float(color_hex)
            font_size  = float(row.get("size") or 11.0)
            is_bold    = bool(row.get("bold", False))
            is_italic  = bool(row.get("italic", False))

            font_name = _select_font(is_bold, is_italic)

            # Insérer le texte traduit en respectant la bbox
            try:
                rc = page.insert_textbox(
                    bbox,
                    translated,
                    fontname  = font_name,
                    fontsize  = font_size,
                    color     = (r, g, b),
                    align     = fitz.TEXT_ALIGN_LEFT,
                )
                if rc < 0:
                    # Texte trop long : ajuster la taille progressivement
                    for shrink in (0.9, 0.8, 0.7, 0.6):
                        page.insert_textbox(
                            bbox, translated,
                            fontname = font_name,
                            fontsize = font_size * shrink,
                            color    = (r, g, b),
                        )
                        if rc >= 0:
                            break
                replaced += 1
            except Exception as exc:
                warnings.append(f"Span {span_id} : insertion échouée — {exc}")
                skipped += 1

        doc.save(str(output_path))
        logger.info("PDF traduit reconstruit : %s (replaced=%d, skipped=%d)",
                    output_path, replaced, skipped)
    finally:
        doc.close()

    return ReconstructionResult(
        output_path    = output_path,
        spans_replaced = replaced,
        spans_skipped  = skipped,
        warnings       = warnings,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hex_to_rgb_float(hex_color: str) -> tuple[float, float, float]:
    if len(hex_color) != 6:
        return (0.0, 0.0, 0.0)
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    return (r, g, b)


def _select_font(bold: bool, italic: bool) -> str:
    """Sélection d'une police standard PyMuPDF selon le style."""
    if bold and italic:
        return "Helvetica-BoldOblique"
    if bold:
        return "Helvetica-Bold"
    if italic:
        return "Helvetica-Oblique"
    return "Helvetica"

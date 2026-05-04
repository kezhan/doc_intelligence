"""
TODO-012 — Consolidation Word + PDF.

Récupère le meilleur des deux formats :
- Structure hiérarchique + table des matières + spans depuis le .docx
- Annotations + commentaires + signatures depuis le .pdf

Aucun LLM. Pure manipulation XML/PyMuPDF.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import pandas as pd

from .parser import WordParseResult, parse_word

logger = logging.getLogger(__name__)


@dataclass
class ConsolidatedDocument:
    """Output unifié Word + PDF."""
    df:           pd.DataFrame                    # paragraphs (depuis Word)
    toc:          list[dict[str, Any]]            # table des matières (Word)
    spans:        list[dict[str, Any]]            # spans avec ID (Word)
    tables:       list[pd.DataFrame]              # tableaux natifs (Word)
    annotations:  list[dict[str, Any]] = field(default_factory=list)  # annot PDF


def consolidate_word_pdf(
    docx_path: str | Path,
    pdf_path:  str | Path,
) -> ConsolidatedDocument:
    """
    TODO-012 — Fusionner Word natif (structure) et PDF (annotations).

    Args:
        docx_path : .docx source
        pdf_path  : équivalent PDF (annoté/signé)

    Returns:
        ConsolidatedDocument avec structure Word + annotations PDF
    """
    word_data   = parse_word(docx_path)
    annotations = _extract_pdf_annotations(pdf_path)

    return ConsolidatedDocument(
        df          = word_data.df,
        toc         = word_data.toc,
        spans       = word_data.spans,
        tables      = word_data.tables,
        annotations = annotations,
    )


def _extract_pdf_annotations(pdf_path: str | Path) -> list[dict[str, Any]]:
    """Extraire toutes les annotations du PDF (commentaires, surlignages, signatures)."""
    annotations: list[dict[str, Any]] = []
    doc = fitz.open(str(pdf_path))

    try:
        for page_num, page in enumerate(doc, start=1):
            for annot in page.annots() or []:
                info = annot.info
                rect = annot.rect
                annotations.append({
                    "page":      page_num,
                    "type":      annot.type[1] if annot.type else "unknown",
                    "content":   info.get("content", ""),
                    "title":     info.get("title", ""),
                    "subject":   info.get("subject", ""),
                    "x0":        round(rect.x0, 2),
                    "y0":        round(rect.y0, 2),
                    "x1":        round(rect.x1, 2),
                    "y1":        round(rect.y1, 2),
                    "modified":  info.get("modDate", ""),
                })
    finally:
        doc.close()

    logger.info("Annotations PDF extraites : %d", len(annotations))
    return annotations

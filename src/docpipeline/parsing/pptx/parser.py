"""
Parsing PowerPoint (.pptx) — section 3.4 du document Faseya.

Sortie : DataFrame standardisé une ligne par fragment de texte de slide,
avec métadonnées (slide, shape, position, style).

Aucun LLM. Utilise python-pptx (XML natif).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class PPTXParseResult:
    df:           pd.DataFrame                # une ligne = un paragraphe de shape
    slide_titles: list[str]                   # titre de chaque slide
    slide_count:  int
    tables:       list[pd.DataFrame]          # tableaux natifs
    notes:        list[str]                   # notes du présentateur


def parse_pptx(pptx_path: str | Path) -> PPTXParseResult:
    """
    Parser un .pptx en DataFrame standardisé.

    Input  : chemin .pptx
    Output : PPTXParseResult avec DataFrame + titres + tableaux + notes
    """
    try:
        from pptx import Presentation
    except ImportError as exc:
        raise ImportError("python-pptx requis. Installer : pip install python-pptx") from exc

    prs = Presentation(str(pptx_path))
    rows:        list[dict[str, Any]] = []
    titles:      list[str]            = []
    tables_list: list[pd.DataFrame]   = []
    notes:       list[str]            = []

    for slide_idx, slide in enumerate(prs.slides, start=1):
        title = _slide_title(slide)
        titles.append(title)

        # Notes du présentateur
        if slide.has_notes_slide:
            note_text = slide.notes_slide.notes_text_frame.text.strip()
            notes.append(note_text)
        else:
            notes.append("")

        for shape_idx, shape in enumerate(slide.shapes):
            # Tableaux natifs
            if shape.has_table:
                tables_list.append(_pptx_table_to_df(shape.table))
                continue

            # Texte
            if shape.has_text_frame:
                for para_idx, para in enumerate(shape.text_frame.paragraphs):
                    text = para.text.strip()
                    if not text:
                        continue
                    rows.append({
                        "slide":       slide_idx,
                        "slide_title": title,
                        "shape":       shape_idx,
                        "paragraph":   para_idx,
                        "text":        text,
                        "level":       para.level,
                        "x":           int(shape.left)   if shape.left   else None,
                        "y":           int(shape.top)    if shape.top    else None,
                        "width":       int(shape.width)  if shape.width  else None,
                        "height":      int(shape.height) if shape.height else None,
                    })

    df = pd.DataFrame(rows)
    logger.info("PPTX parsé : %d slides, %d paragraphes, %d tableaux",
                len(prs.slides), len(df), len(tables_list))

    return PPTXParseResult(
        df           = df,
        slide_titles = titles,
        slide_count  = len(prs.slides),
        tables       = tables_list,
        notes        = notes,
    )


def _slide_title(slide) -> str:
    if slide.shapes.title and slide.shapes.title.has_text_frame:
        return slide.shapes.title.text_frame.text.strip()
    return ""


def _pptx_table_to_df(table) -> pd.DataFrame:
    rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
    if not rows:
        return pd.DataFrame()
    header = rows[0]
    return pd.DataFrame(rows[1:], columns=header)

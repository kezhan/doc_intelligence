"""
TODO-TOC-004 — Extraction de TOC par hyperliens internes.

Deux méthodes, ZERO LLM :
  1. Liens internes  : scan des premières pages pour les hyperliens (kind=1) avec cible page
  2. Numérotation    : lignes "texte … numéro" détectées par regex, footer exclu
"""

from __future__ import annotations

import re
from pathlib import Path

import fitz  # PyMuPDF
import pandas as pd

from ._utils import add_toc_metadata


_CLEAN_LEADING_NUMBERS_RE = re.compile(r"^\s*\d+[.\)]*\s*")
_CLEAN_DOTS_RE = re.compile(r"\.{3,}")
_CLEAN_TRAILING_NUMBER_RE = re.compile(r"[-–—]?\s*\d+\s*$")
_CLEAN_SPACES_RE = re.compile(r"\s+")
_TOC_LINE_PATTERN = re.compile(r"^(.*?)\s*[\.\s]*\s*(\d+)$")


def _clean_toc_text(text: str) -> str:
    """Nettoyer une ligne de TOC : numéros de section, points leaders, numéro de page."""
    text = _CLEAN_LEADING_NUMBERS_RE.sub("", text)
    text = _CLEAN_DOTS_RE.sub(" ", text)
    text = _CLEAN_TRAILING_NUMBER_RE.sub("", text)
    return _CLEAN_SPACES_RE.sub(" ", text).strip()


def extract_toc_from_links(
    pdf_path: str | Path,
    max_pages: int | None = None,
) -> pd.DataFrame:
    """
    TODO-TOC-004a — Extraire les entrées TOC via les hyperliens internes.

    Scanne les `max_pages` premières pages à la recherche de liens internes
    (kind=1) dont la cible est une page du document — signature typique d'un
    TOC cliquable (Word vers PDF, Adobe Acrobat, etc.).

    Input  : chemin PDF, nombre de pages à scanner
    Output : DataFrame colonnes [text, page_num_real, page_num, level, indicator]
             — vide si aucun hyperlien interne n'est trouvé
    """
    toc_entries: list[dict] = []

    with fitz.open(str(pdf_path)) as doc:
        page_limit = doc.page_count if max_pages is None else min(max_pages, doc.page_count)
        for i in range(page_limit):
            page = doc[i]
            for link in page.get_links():
                if link.get("kind") == 1 and "page" in link:
                    raw_text = page.get_textbox(link["from"]).strip()
                    if raw_text:
                        cleaned_text = _clean_toc_text(raw_text)
                        if cleaned_text:
                            toc_entries.append({
                                "text": cleaned_text,
                                "page_num_real": link["page"] + 1,
                            })
    toc_df = pd.DataFrame(toc_entries, columns=["text", "page_num_real"])
    if not toc_df.empty:
        toc_df["page_num"] = toc_df["page_num_real"]
    return add_toc_metadata(toc_df)


def extract_toc_by_numbering(
    pdf_path: str | Path,
    max_pages: int | None = None,
    footer_ratio: float = 0.10,
) -> pd.DataFrame:
    """
    TODO-TOC-004b — Extraire les entrées TOC par pattern "texte … numéro de page".

    Détecte les lignes dont le dernier token est un entier. Ignore la zone
    footer (footer_ratio × hauteur de page) pour ne pas capturer la pagination.

    Input  : chemin PDF, nombre de pages à scanner, ratio footer à ignorer
    Output : DataFrame colonnes [text, page_num_displayed, page_num_real, page_num, level, indicator]
    """
    toc_entries: list[dict] = []

    with fitz.open(str(pdf_path)) as doc:
        page_limit = doc.page_count if max_pages is None else min(max_pages, doc.page_count)
        for i in range(page_limit):
            page = doc[i]
            footer_threshold = page.rect.height * (1 - footer_ratio)

            for block in page.get_text("blocks"):
                x0, y0, x1, y1, text, *_ = block

                if y0 > footer_threshold:
                    continue

                for line in text.splitlines():
                    match = _TOC_LINE_PATTERN.match(line.strip())
                    if match:
                        title = match.group(1).strip()
                        if title:
                            toc_entries.append({
                                "text": title,
                                "page_num_displayed": int(match.group(2)),
                            })
    toc_df = pd.DataFrame(toc_entries, columns=["text", "page_num_displayed"])
    if not toc_df.empty:
        # Sans ancrage de lien interne, on suppose l'égalité affichée/réelle.
        toc_df["page_num_real"] = toc_df["page_num_displayed"]
        toc_df["page_num"] = toc_df["page_num_real"]
    return add_toc_metadata(toc_df)

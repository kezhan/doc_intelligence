"""§2.4 — Scope & structural hints.

L'utilisateur DIT souvent où chercher : « page 1, top-right block »,
« in the exclusions section », « in the recap table near the end ».
On extrait ces hints et on les utilise comme filtres avant retrieval.
"""

from __future__ import annotations

import re

from pydantic import BaseModel


class StructuralHints(BaseModel):
    section_hint: str | None = None
    page_hint: int | None = None
    layout_hint: str | None = None        # "table" | "header" | "image"
    document_version: str | None = None
    jurisdiction: str | None = None
    date_range: tuple[str, str] | None = None


_SECTION_RE  = re.compile(r"section\s+([\w\s]+?)(?=[\.,;]|$)", re.IGNORECASE)
_PAGE_RE     = re.compile(r"page\s+(\d+)", re.IGNORECASE)
_TABLE_KW    = ("table", "tableau", "grid")
_IMAGE_KW    = ("image", "figure", "diagram", "schéma", "schema")
_HEADER_KW   = ("header", "en-tête", "top of page", "top-right")
_FOOTER_KW   = ("footer", "pied de page", "bottom of page")


def extract_hints(question: str) -> StructuralHints:
    """Extrait page / section / layout via regex + mots-clés.

    Pour des hints plus flous (juridiction, version, date), un appel LLM
    structuré pourrait être ajouté ici.
    """
    h = StructuralHints()
    q_lower = question.lower()

    if m := _SECTION_RE.search(question):
        h.section_hint = m.group(1).strip()
    if m := _PAGE_RE.search(question):
        h.page_hint = int(m.group(1))

    if any(kw in q_lower for kw in _TABLE_KW):
        h.layout_hint = "table"
    elif any(kw in q_lower for kw in _IMAGE_KW):
        h.layout_hint = "image"
    elif any(kw in q_lower for kw in _HEADER_KW):
        h.layout_hint = "header"
    elif any(kw in q_lower for kw in _FOOTER_KW):
        h.layout_hint = "footer"

    return h

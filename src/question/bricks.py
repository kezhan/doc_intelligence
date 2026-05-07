"""Registre de briques — chaque capacité d'extraction est une entrée du dict `BRICKS`.

Chaque brique est un objet immuable qui déclare :
  - son nom (clé d'activation),
  - sa cible dans le JSON (`retrieval` ou `generation`),
  - son extracteur `run(question, context) -> dict | None`,
  - les types de document compatibles (vide = tous),
  - si elle nécessite un appel LLM.

Ajouter une brique = ajouter une entrée. Le pipeline ne change pas.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .disambiguation import extract_disambiguation
from .format import extract_format_constraint
from .keywords import extract_anchor_keywords
from .rewrite import rewrite_query
from .scope import extract_hints

BrickRunner = Callable[[str, dict[str, Any]], dict[str, Any] | None]


@dataclass(frozen=True)
class Brick:
    name: str
    target: str                                       # "retrieval" | "generation"
    run: BrickRunner
    compatible_doc_types: tuple[str, ...] = ()        # vide = tous
    requires_llm: bool = False
    description: str = ""


# ── Wrappers : adapter chaque helper individuel au contrat Brick ──────────────

def _run_rewrite(q: str, ctx: dict) -> dict | None:
    rewrites = rewrite_query(q, ctx.get("domain_hint", ""))
    # rewrite_query retourne [q] en fallback no-LLM — on ne pollue pas le JSON dans ce cas
    if not rewrites or rewrites == [q]:
        return None
    return {"rewrites": rewrites}


def _run_anchors(q: str, _ctx: dict) -> dict | None:
    kw = extract_anchor_keywords(q)
    return {"anchor_keywords": kw} if kw else None


def _run_page_hint(q: str, _ctx: dict) -> dict | None:
    h = extract_hints(q)
    return {"page_hint": h.page_hint} if h.page_hint is not None else None


def _run_section_hint(q: str, _ctx: dict) -> dict | None:
    h = extract_hints(q)
    return {"section_hint": h.section_hint} if h.section_hint else None


def _run_layout_hint(q: str, _ctx: dict) -> dict | None:
    h = extract_hints(q)
    return {"layout_hint": h.layout_hint} if h.layout_hint else None


def _run_format(q: str, _ctx: dict) -> dict | None:
    f = extract_format_constraint(q)
    return {"format_constraint": f} if f else None


def _run_disambig(q: str, _ctx: dict) -> dict | None:
    instruction, distractors = extract_disambiguation(q)
    if not distractors:
        return None
    return {"disambiguation": instruction, "must_distinguish": distractors}


# ── Registre central ──────────────────────────────────────────────────────────

BRICKS: dict[str, Brick] = {
    "rewrite": Brick(
        name="rewrite",
        target="retrieval",
        run=_run_rewrite,
        requires_llm=True,
        description="Reformule la question dans le vocabulaire du document (HyDE-lite).",
    ),
    "anchor_keywords": Brick(
        name="anchor_keywords",
        target="retrieval",
        run=_run_anchors,
        description="Extrait codes/IDs/acronymes pour l'index lexical (BM25).",
    ),
    "page_hint": Brick(
        name="page_hint",
        target="retrieval",
        run=_run_page_hint,
        compatible_doc_types=("pdf", "pptx"),   # NOT word, NOT excel, NOT email
        description="Extrait un numéro de page mentionné dans la question.",
    ),
    "section_hint": Brick(
        name="section_hint",
        target="retrieval",
        run=_run_section_hint,
        compatible_doc_types=("pdf", "word", "pptx"),
        description="Extrait un nom/numéro de section mentionné dans la question.",
    ),
    "layout_hint": Brick(
        name="layout_hint",
        target="retrieval",
        run=_run_layout_hint,
        description="Extrait un indice de mise en page (table, header, footer, image).",
    ),
    "format": Brick(
        name="format",
        target="generation",
        run=_run_format,
        description="Détecte une contrainte de format de sortie (date ISO, JSON, ...).",
    ),
    "disambiguation": Brick(
        name="disambiguation",
        target="generation",
        run=_run_disambig,
        description="Détecte 'X, not Y' et fournit instruction + distractors au générateur.",
    ),
}


def list_bricks(doc_type: str | None = None) -> list[Brick]:
    """Liste les briques compatibles avec un document_type (ou toutes si None)."""
    if doc_type is None:
        return list(BRICKS.values())
    return [
        b for b in BRICKS.values()
        if not b.compatible_doc_types or doc_type in b.compatible_doc_types
    ]

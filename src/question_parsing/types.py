"""Modèles Pydantic — pivot de tout le chapitre 6.

Une question utilisateur produit DEUX artefacts allant à deux étapes différentes :
retrieval (matching de similarité) et generation (lecture + raisonnement).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RetrievalQuery(BaseModel):
    """Ce que le retriever consomme — ne contient AUCUNE instruction négative."""

    main_query: str
    rewrites: list[str] = Field(default_factory=list)
    anchor_keywords: list[str] = Field(default_factory=list)
    section_hint: str | None = None
    page_hint: int | None = None
    layout_hint: str | None = None  # "table" | "header" | "footer" | "image"
    scope: str = "default"          # "single_document" | "corpus" | "subset"


class GenerationBrief(BaseModel):
    """Ce que le générateur consomme — préserve la formulation utilisateur."""

    original_question: str
    format_constraint: str | None = None
    disambiguation: str | None = None
    must_distinguish: list[str] = Field(default_factory=list)


class ParsedQuestion(BaseModel):
    retrieval: RetrievalQuery
    generation: GenerationBrief

"""
src.question — Chapitre 6 : Understanding the Question Before Searching.

Sépare une question utilisateur en deux artefacts structurés :

  - RetrievalQuery   → ce que le retriever consomme (rewrites, anchors, hints)
  - GenerationBrief  → ce que le générateur consomme (question originale,
                       format, disambiguation, distractors)

Point d'entrée :  from src.question.pipeline import understand_question
"""

from .types import RetrievalQuery, GenerationBrief, ParsedQuestion

__all__ = ["RetrievalQuery", "GenerationBrief", "ParsedQuestion"]

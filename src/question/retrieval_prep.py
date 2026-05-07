"""§2.5 — Assemblage de la RetrievalQuery.

Tous les helpers § 2.1–2.4 convergent ici pour produire l'objet structuré
que le retriever consomme.
"""

from __future__ import annotations

from .keywords import extract_anchor_keywords
from .rewrite import rewrite_query
from .scope import extract_hints
from .spell import correct_spelling
from .types import RetrievalQuery


def prepare_retrieval_query(question: str, domain_hint: str = "") -> RetrievalQuery:
    """Pipeline complet de préparation retrieval.

    Note : on appelle `extract_hints` une seule fois (le chapitre l'appelle 3
    fois, c'est une coquille — chaque appel est identique).
    """
    corrected = correct_spelling(question)
    hints = extract_hints(corrected)

    return RetrievalQuery(
        main_query=corrected,
        rewrites=rewrite_query(corrected, domain_hint),
        anchor_keywords=extract_anchor_keywords(corrected),
        section_hint=hints.section_hint,
        page_hint=hints.page_hint,
        layout_hint=hints.layout_hint,
    )

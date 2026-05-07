"""§6 — Demander à l'utilisateur quand un référent reste flou.

Règle : si la question contient un référent qui exige du contexte (this, that,
le, la, the latest, last year's, the cap) et que ce contexte n'est pas dans
l'historique de conversation, demander.
"""

from __future__ import annotations

_REFERENTS = (
    "this", "that", "the cap", "the limit", "the latest",
    "last year", "the same", "the previous",
    # FR
    "celui-ci", "celui-là", "celle-ci", "celle-là",
    "le plafond", "la limite", "la dernière version", "l'an passé",
)


def needs_clarification(question: str, conversation_history: list | None = None) -> bool:
    """Heuristique : référent ambigu + question courte + pas d'historique."""
    if conversation_history:
        return False
    q = question.lower().strip()
    if len(q) > 60:
        return False
    return any(ref in q for ref in _REFERENTS)


def suggest_clarifications(question: str) -> list[str]:
    """Suggestions courtes à proposer à l'utilisateur."""
    q = question.lower()
    if "cap" in q or "limit" in q or "plafond" in q or "limite" in q:
        return [
            "Liability cap?",
            "Indemnification cap?",
            "Coverage limit per claim?",
            "Aggregate limit?",
        ]
    if "version" in q or "latest" in q or "dernière" in q:
        return [
            "Latest signed version?",
            "Latest draft?",
            "Latest as of a specific date?",
        ]
    if "compare" in q or "last year" in q or "l'an passé" in q:
        return [
            "Compare with which year/document?",
            "Compare on which dimension (price, scope, parties)?",
        ]
    return [
        "Could you clarify which document?",
        "Could you clarify which concept exactly?",
    ]

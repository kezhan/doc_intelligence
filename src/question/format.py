"""§3.2 — Format constraint.

Une contrainte de format n'a RIEN à voir avec retrieval. Elle va dans le
prompt de génération.
"""

from __future__ import annotations


def extract_format_constraint(question: str) -> str | None:
    """Détecte une demande de format explicite."""
    q = question.lower()

    if "yyyy-mm-dd" in q or "iso 8601" in q or " iso " in q:
        return "ISO 8601 date (YYYY-MM-DD)"
    if "json" in q:
        return "valid JSON"
    if any(kw in q for kw in ["in euros", "in dollars", "as a number", "en euros", "en dollars"]):
        return "numeric value with explicit currency"
    if "in one sentence" in q or "en une phrase" in q:
        return "single sentence, no preamble"
    if "bullet" in q or "list" in q or "liste" in q:
        return "bullet list"
    return None

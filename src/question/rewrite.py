"""§2.2 — Vocabulary bridge.

Le user dit « what happens if we exit early », le document dit « early
termination provisions ». Variante de HyDE : on génère le langage qui
*entoure* la réponse, pas une fausse réponse.
"""

from __future__ import annotations

from ._llm import call_llm


def rewrite_query(question: str, domain_hint: str = "") -> list[str]:
    """3 à 5 reformulations dans le vocabulaire du document.

    Sans OPENAI_API_KEY : retourne `[question]` seule (pas de reformulation).
    """
    prompt = f"""You are translating a user question into search queries that match
how the answer would be phrased in a {domain_hint or 'professional'} document.
Return 3 to 5 alternative phrasings. Use vocabulary the document is likely to use,
not the user's casual phrasing. Output one phrasing per line, no numbering.

User question: {question}"""
    out = call_llm(prompt)
    if out is None:
        return [question]
    return [line.strip() for line in out.splitlines() if line.strip()]

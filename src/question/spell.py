"""§2.1 — Spell correction. Fixe typos & grammaire avant retrieval.

Embeddings tolèrent un peu de bruit ; BM25 et le matching exact sur la TOC
le tolèrent beaucoup moins. Une passe LLM brève suffit.
"""

from __future__ import annotations

from ._llm import call_llm


def correct_spelling(question: str) -> str:
    """Corrige typos et grammaire sans changer le sens.

    Sans OPENAI_API_KEY : retourne la question telle quelle (no-op gracieux).
    """
    prompt = f"""Fix any typos and grammar mistakes in the question below.
Do not change the meaning. Do not add or remove information. Return only
the corrected question, nothing else.

Question: {question}"""
    out = call_llm(prompt)
    return out if out is not None else question

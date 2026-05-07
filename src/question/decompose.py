"""§5 — Décomposition multi-étapes.

Certaines questions ne peuvent pas être satisfaites par UN passage isolé,
quelle que soit la qualité du retriever. Il faut les découper en sous-questions
exécutées en séquence (avec dépendances).
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from ._llm import call_llm


class SubQuestion(BaseModel):
    text: str
    depends_on: list[int] = Field(default_factory=list)
    operation: str = "retrieve"   # "retrieve" | "compare" | "aggregate" | "filter"


class DecomposedQuery(BaseModel):
    original: str
    sub_questions: list[SubQuestion]


_PROMPT = """Decompose the user question into 1 to 4 sub-questions executable in order.
Output strict JSON with this schema:
{{
  "sub_questions": [
    {{"text": "...", "depends_on": [], "operation": "retrieve|compare|aggregate|filter"}}
  ]
}}

Rules:
- A simple field-extraction question stays as a single sub-question with operation "retrieve".
- A comparison ("are A and B consistent?") splits into two retrievals + one "compare".
- A conditional ("does X exist, and if so what is its Y?") splits into the boolean retrieval
  then a dependent retrieval.
- "depends_on" lists 0-based indices of sub-questions whose results are needed.

User question: {question}"""


def decompose_query(question: str) -> DecomposedQuery:
    """Décompose via LLM. Fallback gracieux : une seule sous-question = la question elle-même."""
    raw = call_llm(_PROMPT.format(question=question))
    if raw is None:
        return DecomposedQuery(
            original=question,
            sub_questions=[SubQuestion(text=question, operation="retrieve")],
        )

    try:
        # Le LLM peut entourer le JSON de fences ; on enlève ce qui dépasse.
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw.strip())
        subs = [SubQuestion(**sq) for sq in data.get("sub_questions", [])]
        if not subs:
            raise ValueError("empty decomposition")
    except (json.JSONDecodeError, ValueError, TypeError):
        subs = [SubQuestion(text=question, operation="retrieve")]

    return DecomposedQuery(original=question, sub_questions=subs)

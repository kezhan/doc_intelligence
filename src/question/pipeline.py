"""§7 — Pipeline complet : raw question → ParsedQuestion(s).

Orchestration conditionnelle :
  - spell correction systématique
  - clarification SI référent ambigu et pas d'historique → arrêt anticipé
  - décomposition SI intent ∈ {compare, aggregate, conditional}
  - prepare_retrieval_query + GenerationBrief par sous-question
"""

from __future__ import annotations

from typing import Any

from .classify import classify_intent
from .clarify import needs_clarification, suggest_clarifications
from .decompose import decompose_query
from .disambiguation import extract_disambiguation
from .format import extract_format_constraint
from .retrieval_prep import prepare_retrieval_query
from .spell import correct_spelling
from .types import GenerationBrief, ParsedQuestion


def understand_question(
    question: str,
    conversation_history: list[Any] | None = None,
    domain_hint: str = "",
) -> dict[str, Any]:
    """Transforme une question utilisateur brute en plan d'exécution.

    Returns:
        dict :
          - {"action": "clarify", "options": [...]}                 # si flou
          - {"action": "retrieve_and_generate", "intent": "...",
             "parsed": list[ParsedQuestion]}                        # sinon
    """
    corrected = correct_spelling(question)

    if needs_clarification(corrected, conversation_history):
        return {"action": "clarify", "options": suggest_clarifications(corrected)}

    intent = classify_intent(corrected)

    if intent in ("compare", "aggregate", "conditional"):
        sub_questions = [sq.text for sq in decompose_query(corrected).sub_questions]
    else:
        sub_questions = [corrected]

    parsed: list[ParsedQuestion] = []
    for sq in sub_questions:
        instruction, distractors = extract_disambiguation(sq)
        parsed.append(ParsedQuestion(
            retrieval=prepare_retrieval_query(sq, domain_hint),
            generation=GenerationBrief(
                original_question=sq,
                format_constraint=extract_format_constraint(sq),
                disambiguation=instruction,
                must_distinguish=distractors,
            ),
        ))

    return {"action": "retrieve_and_generate", "intent": intent, "parsed": parsed}

"""Point d'entrée unique : `understand_question(question, ...) -> list[dict]`.

Orchestration en quatre temps :

  1. Spell correction (sauf si `enable={"spell": False}`).
  2. Clarification : si la question contient un référent flou et qu'il n'y a
     pas d'historique conversationnel → on rend une seule entrée avec
     `_meta.action == "clarify"` et des options à proposer.
  3. Classification d'intent + décomposition éventuelle (questions composées).
  4. Pour chaque sous-question, on tourne les briques actives (preset par
     `document_type` + override `enable`) et on assemble le JSON.

Le JSON ne contient que les champs réellement populés. Pas de `null`.
"""

from __future__ import annotations

from typing import Any

from .bricks import BRICKS
from .classify import classify_intent
from .clarify import needs_clarification, suggest_clarifications
from .decompose import decompose_query
from .presets import resolve_active
from .spell import correct_spelling

COMPOUND_INTENTS = frozenset({"compare", "aggregate", "conditional"})


def understand_question(
    question: str,
    *,
    document_type: str = "pdf",
    enable: dict[str, bool] | None = None,
    domain_hint: str = "",
    conversation_history: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """Transforme une question utilisateur brute en plan d'exécution structuré.

    Args:
        question:             la question de l'utilisateur, brute.
        document_type:        type du document cible — pilote le preset par défaut.
        enable:               override fin par brique : `{"page_hint": False, "my_brick": True}`.
                              S'applique aussi aux étapes d'orchestration : `spell`, `clarify`,
                              `decompose`.
        domain_hint:          domaine métier passé aux briques LLM (ex: "insurance policy").
        conversation_history: historique de conversation, neutralise la clarification.

    Returns:
        Liste de dicts. Toujours une liste : 1 question simple = 1 entrée,
        question composée = N entrées indépendantes. Une demande de
        clarification = 1 entrée avec `_meta.action == "clarify"`.
    """
    enable = dict(enable or {})

    # ── 1. Spell correction ──────────────────────────────────────────────────
    if enable.pop("spell", True):
        question = correct_spelling(question)

    # ── 2. Clarification ─────────────────────────────────────────────────────
    if enable.pop("clarify", True) and needs_clarification(question, conversation_history):
        return [{
            "_meta": {
                "action": "clarify",
                "document_type": document_type,
            },
            "options": suggest_clarifications(question),
        }]

    # ── 3. Intent + décomposition ────────────────────────────────────────────
    intent = classify_intent(question)
    do_decompose = enable.pop("decompose", True) and intent in COMPOUND_INTENTS
    sub_questions = (
        [sq.text for sq in decompose_query(question).sub_questions]
        if do_decompose
        else [question]
    )

    # ── 4. Briques actives + extraction par sous-question ────────────────────
    active = resolve_active(document_type, enable)
    ctx = {"domain_hint": domain_hint, "document_type": document_type}

    return [
        _run_extraction(sq, document_type, active, ctx, intent)
        for sq in sub_questions
    ]


def _run_extraction(
    q: str,
    doc_type: str,
    active_bricks: list[str],
    ctx: dict[str, Any],
    intent: str,
) -> dict[str, Any]:
    """Tourne les briques actives et assemble le JSON pour UNE sous-question."""
    output: dict[str, Any] = {
        "retrieval":  {"main_query": q},
        "generation": {"original_question": q},
        "_meta": {
            "intent": intent,
            "document_type": doc_type,
            "bricks_active": [],
        },
    }

    for name in active_bricks:
        brick = BRICKS.get(name)
        if brick is None:
            continue   # brique listée dans enable={...} mais absente du registre
        if brick.compatible_doc_types and doc_type not in brick.compatible_doc_types:
            continue   # incompatible avec ce document_type

        result = brick.run(q, ctx)
        if not result:
            continue

        output[brick.target].update(result)
        output["_meta"]["bricks_active"].append(name)

    return output

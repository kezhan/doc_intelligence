"""
src.question — Chapitre 6 : Understanding the Question Before Searching.

Conception : design article dans [docs/06_question_layer.md](../../docs/06_question_layer.md).

API publique :

    from src.question import understand_question

    plan = understand_question(
        "Quelle est la prime sur ce contrat ?",
        document_type="pdf",
    )
    # → [ { "retrieval": {...}, "generation": {...}, "_meta": {...} } ]

Pour étendre :

    from src.question import BRICKS, PRESETS, Brick

    BRICKS["my_brick"] = Brick("my_brick", "retrieval", _run_my_brick)
    PRESETS["pdf"].append("my_brick")
"""

from .bricks import BRICKS, Brick, list_bricks
from .pipeline import understand_question
from .presets import PRESETS, preset_for, resolve_active

__all__ = [
    "understand_question",
    "BRICKS",
    "Brick",
    "list_bricks",
    "PRESETS",
    "preset_for",
    "resolve_active",
]

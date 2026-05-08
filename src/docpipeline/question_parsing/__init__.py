"""docpipeline.question_parsing — version compatible drop-in avec src.question."""

from .question_parsing import (
    BRICKS,
    PRESETS,
    Brick,
    classify_intent,
    extract_anchor_keywords,
    extract_answer_shape,
    extract_disambiguation,
    extract_format_constraint,
    extract_hints,
    parse_question,
    preset_for,
    resolve_active,
)

__all__ = [
    "parse_question",
    "BRICKS",
    "PRESETS",
    "Brick",
    "classify_intent",
    "extract_anchor_keywords",
    "extract_answer_shape",
    "extract_disambiguation",
    "extract_format_constraint",
    "extract_hints",
    "preset_for",
    "resolve_active",
]

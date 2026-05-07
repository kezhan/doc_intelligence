"""Question sub-package — parser une question utilisateur en JSON structuré."""

from .question_parsing import (
    Disambiguation,
    ParsedQuestion,
    StructuralHints,
    classify_intent,
    extract_anchor_keywords,
    extract_disambiguation,
    extract_format_constraint,
    extract_hints,
    parse_question,
)

__all__ = [
    "parse_question",
    "extract_hints",
    "extract_anchor_keywords",
    "extract_format_constraint",
    "extract_disambiguation",
    "classify_intent",
    "ParsedQuestion",
    "StructuralHints",
    "Disambiguation",
]

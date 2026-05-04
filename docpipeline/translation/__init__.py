"""Translation pipeline — style-preserving document translation."""

from .glossary import GlossaryEntry, Glossary, detect_business_terms, decide_translate_or_keep
from .word_translator import translate_word

__all__ = [
    "GlossaryEntry",
    "Glossary",
    "detect_business_terms",
    "decide_translate_or_keep",
    "translate_word",
]

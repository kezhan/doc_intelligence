"""Translation pipeline — style-preserving document translation."""

from .glossary import GlossaryEntry, Glossary, detect_business_terms, decide_translate_or_keep
from .pdf_reconstructor import reconstruct_pdf_translation, ReconstructionResult
from .side_by_side import render_side_by_side, SideBySideResult
from .word_translator import translate_word

__all__ = [
    "GlossaryEntry",
    "Glossary",
    "detect_business_terms",
    "decide_translate_or_keep",
    "translate_word",
    "reconstruct_pdf_translation",
    "ReconstructionResult",
    "render_side_by_side",
    "SideBySideResult",
]

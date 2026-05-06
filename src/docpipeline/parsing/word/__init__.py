"""Word parsing sub-package — native XML exploitation."""

from .consolidator import ConsolidatedDocument, consolidate_word_pdf
from .parser import parse_word, WordParseResult

__all__ = [
    "parse_word",
    "WordParseResult",
    "consolidate_word_pdf",
    "ConsolidatedDocument",
]

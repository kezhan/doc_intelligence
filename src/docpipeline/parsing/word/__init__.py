"""Word parsing sub-package — native XML exploitation."""

# Nouvelle API (parse_word.py) — version exhaustive avec apply_changes
from .parse_word import apply_changes, parse_word

# Legacy (parser.py + consolidator.py) — gardés pour ne pas casser les
# consommateurs existants. Accessibles via leurs chemins directs si besoin :
#   from docpipeline.parsing.word.parser import parse_word as parse_word_legacy
from .consolidator import ConsolidatedDocument, consolidate_word_pdf
from .parser import WordParseResult

__all__ = [
    # Nouvelle API
    "parse_word",
    "apply_changes",
    # Legacy
    "WordParseResult",
    "consolidate_word_pdf",
    "ConsolidatedDocument",
]

"""PowerPoint parsing sub-package — extraction native via python-pptx."""

# Nouvelle API (parse_pptx.py) — version exhaustive avec runs_df + styles complets
from .parse_pptx import parse_pptx

# Legacy (parser.py) — gardé pour ne pas casser les consommateurs existants.
# Accessible via son chemin direct si besoin :
#   from docpipeline.parsing.pptx.parser import parse_pptx as parse_pptx_legacy
from .parser import PPTXParseResult

__all__ = [
    "parse_pptx",
    "PPTXParseResult",
]

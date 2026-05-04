"""PPTX parsing — un slide = un groupe de lignes."""

from .parser import parse_pptx, PPTXParseResult

__all__ = ["parse_pptx", "PPTXParseResult"]

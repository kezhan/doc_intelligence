"""Email parsing — .eml et .msg."""

from .parser import parse_email, EmailParseResult

__all__ = ["parse_email", "EmailParseResult"]

"""Regex patterns and text-matching utilities for TOC detection."""

from __future__ import annotations

import re

TOC_KEYWORDS: list[str] = [
    "sommaire",
    "table des matieres",
    "table des matières",
    "table of contents",
    "contents",
    "inhaltsverzeichnis",
]

_DOTTED_LEADER_RE = re.compile(r".+\.{4,}\s*\d*\s*$", re.MULTILINE)
_LINE_ENDING_WITH_NUMBER_RE = re.compile(r"\d+\s*$")
_HIERARCHICAL_RE = re.compile(
    r"^\s*\d+(?:\.\d+)*(?:[.\)]\s+|\s+)\S",
    re.MULTILINE,
)
_SHORT_LINE_MAX_LEN = 60
NUMERIC_LINE_RATIO_THRESHOLD: float = 0.30


def has_toc_keyword(text: str) -> bool:
    """Check whether text contains a TOC keyword.

    Args:
        text: Page text.

    Returns:
        True when a known TOC keyword is found.
    """
    normalised = text.lower()[:500]
    return any(keyword in normalised for keyword in TOC_KEYWORDS)


def find_dotted_leader_lines(text: str) -> list[str]:
    """Extract dotted-leader lines from page text.

    Args:
        text: Page text.

    Returns:
        Matching lines such as ``Introduction ........ 3``.
    """
    return _DOTTED_LEADER_RE.findall(text)


def find_lines_ending_with_number(text: str) -> list[str]:
    """Extract non-empty lines ending with digits.

    Args:
        text: Page text.

    Returns:
        Lines where the trailing token is numeric (e.g. ``Section 12``).
    """
    return [line for line in text.splitlines() if line.strip() and _LINE_ENDING_WITH_NUMBER_RE.search(line)]


def find_hierarchical_structure(text: str) -> list[str]:
    """Extract lines with hierarchical numbering prefixes.

    Args:
        text: Page text.

    Returns:
        Lines starting with patterns like ``1.``, ``1.2``, ``2.3.1``.
    """
    return _HIERARCHICAL_RE.findall(text)


def calculate_numeric_line_end_ratio(text: str) -> float:
    """Compute ratio of non-empty lines that end with a numeric token.

    Args:
        text: Page text.

    Returns:
        Value in ``[0, 1]``.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return 0.0

    numeric_endings = sum(1 for line in lines if _LINE_ENDING_WITH_NUMBER_RE.search(line))
    return numeric_endings / len(lines)


def calculate_short_line_density(text: str) -> float:
    """Compute the share of short non-empty lines.

    Args:
        text: Page text.

    Returns:
        Ratio of non-empty lines with length below the configured threshold.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return 0.0

    short = sum(1 for line in lines if len(line.strip()) <= _SHORT_LINE_MAX_LEN)
    return short / len(lines)

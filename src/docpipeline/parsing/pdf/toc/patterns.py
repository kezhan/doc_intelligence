"""Regex patterns and text-matching utilities for TOC detection."""

from __future__ import annotations

import re

TOC_KEYWORDS: list[str] = [
    "sommaire",
    "table des matières",
    "table of contents",
    "contents",
    "inhaltsverzeichnis",
]

_DOTTED_LEADER_RE = re.compile(r".+\.{3,}\s*\d*\s*$", re.MULTILINE)
_LINE_ENDING_WITH_NUMBER_RE = re.compile(r".+[\s.\-–—]\d{1,3}\s*$", re.MULTILINE)
_HIERARCHICAL_RE = re.compile(
    r"^\s*\d+(?:\.\d+)*(?:[.\)]\s+|\s+)\S",
    re.MULTILINE,
)
_SHORT_LINE_MAX_LEN = 60


def has_toc_keyword(text: str) -> bool:
    """Return True if the text contains a recognised TOC keyword."""
    normalised = text.lower()
    return any(keyword in normalised for keyword in TOC_KEYWORDS)


def find_dotted_leader_lines(text: str) -> list[str]:
    """Return lines that contain dotted leaders, e.g. ``Introduction ........ 3``."""
    return _DOTTED_LEADER_RE.findall(text)


def find_lines_ending_with_number(text: str) -> list[str]:
    """Return lines ending with a likely page number."""
    return _LINE_ENDING_WITH_NUMBER_RE.findall(text)


def find_hierarchical_structure(text: str) -> list[str]:
    """Return lines that start with a hierarchical numbering pattern."""
    return _HIERARCHICAL_RE.findall(text)


def calculate_short_line_density(text: str) -> float:
    """Return the fraction of non-empty lines shorter than the TOC-line threshold."""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return 0.0

    short = sum(1 for line in lines if len(line.strip()) <= _SHORT_LINE_MAX_LEN)
    return short / len(lines)

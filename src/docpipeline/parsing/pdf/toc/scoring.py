"""Scoring logic for heuristic PDF TOC detection."""

from __future__ import annotations

from . import patterns

WEIGHT_KEYWORD: float = 0.40
WEIGHT_DOTTED_LEADERS: float = 0.30
WEIGHT_LINES_WITH_NUMBER: float = 0.20
WEIGHT_HIERARCHICAL: float = 0.20
WEIGHT_SHORT_LINE_DENSITY: float = 0.10

MIN_OCCURRENCES: int = 3
SHORT_LINE_DENSITY_THRESHOLD: float = 0.60


def score_page(text: str) -> tuple[float, list[str]]:
    """Compute a TOC-likelihood score for a single page's text."""
    raw_score = 0.0
    signals: list[str] = []

    if patterns.has_toc_keyword(text):
        raw_score += WEIGHT_KEYWORD
        signals.append("TOC keyword detected")

    dotted = patterns.find_dotted_leader_lines(text)
    if len(dotted) >= MIN_OCCURRENCES:
        raw_score += WEIGHT_DOTTED_LEADERS
        signals.append(f"Dotted leader patterns found ({len(dotted)} occurrences)")

    numbered = patterns.find_lines_ending_with_number(text)
    if len(numbered) >= MIN_OCCURRENCES:
        raw_score += WEIGHT_LINES_WITH_NUMBER
        signals.append(f"Multiple lines ending with page numbers ({len(numbered)} occurrences)")

    hierarchical = patterns.find_hierarchical_structure(text)
    if len(hierarchical) >= MIN_OCCURRENCES:
        raw_score += WEIGHT_HIERARCHICAL
        signals.append(f"Hierarchical numbering structure detected ({len(hierarchical)} entries)")

    density = patterns.calculate_short_line_density(text)
    if density > SHORT_LINE_DENSITY_THRESHOLD:
        raw_score += WEIGHT_SHORT_LINE_DENSITY
        signals.append(f"High short-line density ({density:.0%})")

    return min(raw_score, 1.0), signals

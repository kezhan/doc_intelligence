"""Scoring logic for heuristic PDF TOC detection."""

from __future__ import annotations

from . import patterns

WEIGHT_KEYWORD: int = 3
WEIGHT_DOTTED_LEADERS: int = 2
WEIGHT_NUMERIC_LINE_RATIO: int = 2
WEIGHT_LINK_DENSITY: int = 2
WEIGHT_EARLY_PAGE_POSITION: int = 1

SELECTION_THRESHOLD: float = 3.0
MIN_DOTTED_LEADERS: int = 1
LINK_DENSITY_MIN_COUNT: int = 5
EARLY_PAGE_MAX_NUMBER: int = 15


def score_page(
    text: str,
    *,
    page_number: int | None = None,
    link_count: int = 0,
) -> tuple[float, list[str]]:
    """Compute TOC score for one page using weighted heuristics.

    Args:
        text: Page text.
        page_number: One-based page number in the PDF.
        link_count: Number of internal links (PyMuPDF ``kind == 1``) found on
            this page.

    Returns:
        Tuple of ``(score, signals)`` where score is additive using the
        configured weights.
    """
    raw_score = 0.0
    signals: list[str] = []

    if patterns.has_toc_keyword(text):
        raw_score += WEIGHT_KEYWORD
        signals.append("TOC keyword detected")

    dotted = patterns.find_dotted_leader_lines(text)
    if len(dotted) >= MIN_DOTTED_LEADERS:
        raw_score += WEIGHT_DOTTED_LEADERS
        signals.append(f"Dotted leader patterns found ({len(dotted)} occurrences)")

    numeric_ratio = patterns.calculate_numeric_line_end_ratio(text)
    if numeric_ratio > patterns.NUMERIC_LINE_RATIO_THRESHOLD:
        raw_score += WEIGHT_NUMERIC_LINE_RATIO
        signals.append(
            f"High numeric line-end ratio ({numeric_ratio:.0%} > {patterns.NUMERIC_LINE_RATIO_THRESHOLD:.0%})"
        )

    if link_count > LINK_DENSITY_MIN_COUNT:
        raw_score += WEIGHT_LINK_DENSITY
        signals.append(f"High internal-link density ({link_count} links)")

    if page_number is not None and page_number < EARLY_PAGE_MAX_NUMBER:
        raw_score += WEIGHT_EARLY_PAGE_POSITION
        signals.append(f"Early page position bonus (page {page_number} < {EARLY_PAGE_MAX_NUMBER})")

    return raw_score, signals

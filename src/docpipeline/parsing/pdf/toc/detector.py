"""Heuristic table-of-contents detection for PDF files.

This module is the public orchestrator.  It keeps the existing
``docpipeline.parsing.pdf.toc.detect_toc`` API while using the modular
reader/scoring/model split from the standalone TOC detector package.
"""

from __future__ import annotations

from pathlib import Path

from .models import PageAnalysis, TocDetectionResult
from .reader import extract_text_from_first_pages
from .scoring import SELECTION_THRESHOLD, score_page

DEFAULT_THRESHOLD: float = SELECTION_THRESHOLD


def detect_toc(
    pdf_path: str | Path,
    max_pages: int | None = None,
    threshold: float = DEFAULT_THRESHOLD,
) -> TocDetectionResult:
    """Detect whether a PDF contains a likely table of contents.

    Args:
        pdf_path: Path to the PDF.
        max_pages: Maximum number of pages to scan from the start of the
            document. If ``None``, scan all pages.
        threshold: Minimum score for selecting a TOC page. Default is ``3``
            on the additive scale. For backward compatibility, values in
            ``[0, 1]`` are interpreted as normalized thresholds and mapped to
            the additive scale.

    Returns:
        A ``TocDetectionResult`` with confidence, selected page numbers, and a
        human-readable reason built from triggered signals.
    """
    raw_pages = extract_text_from_first_pages(pdf_path, max_pages=max_pages)

    analyses: list[PageAnalysis] = []
    for raw_page in raw_pages:
        page_text = str(raw_page["text"])
        page_score, page_signals = score_page(
            page_text,
            page_number=int(raw_page["page_number"]),
            link_count=int(raw_page.get("link_count", 0)),
        )
        analyses.append(
            PageAnalysis(
                page_number=int(raw_page["page_number"]),
                text=page_text,
                score=page_score,
                signals=page_signals,
            )
        )

    effective_threshold = threshold * SELECTION_THRESHOLD if 0.0 <= threshold <= 1.0 else threshold
    toc_pages = [analysis.page_number for analysis in analyses if analysis.score >= effective_threshold]
    confidence = max((analysis.score for analysis in analyses), default=0.0)

    all_signals = [
        signal
        for analysis in analyses
        if analysis.score >= effective_threshold
        for signal in analysis.signals
    ]
    unique_signals = list(dict.fromkeys(all_signals))
    reason = "; ".join(unique_signals) if unique_signals else "No significant TOC signals found"

    return TocDetectionResult(
        has_toc=bool(toc_pages),
        confidence=round(confidence, 4),
        toc_pages=toc_pages,
        reason=reason,
    )

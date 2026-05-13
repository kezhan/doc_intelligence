"""Heuristic table-of-contents detection for PDF files.

This module is the public orchestrator.  It keeps the existing
``docpipeline.parsing.pdf.toc.detect_toc`` API while using the modular
reader/scoring/model split from the standalone TOC detector package.
"""

from __future__ import annotations

from pathlib import Path

from .models import PageAnalysis, TocDetectionResult
from .reader import DEFAULT_MAX_PAGES, extract_text_from_first_pages
from .scoring import score_page

DEFAULT_THRESHOLD: float = 0.50


def detect_toc(
    pdf_path: str | Path,
    max_pages: int | None = None,
    threshold: float = DEFAULT_THRESHOLD,
) -> TocDetectionResult:
    """
    Detect whether a PDF contains a likely table of contents.

    By default the full document is inspected; pass ``max_pages`` to restrict
    the scan to the first pages only. Each page receives a
    score in ``[0, 1]`` based on textual signals: TOC keywords, dotted leaders,
    lines ending with page numbers, hierarchical numbering and short-line
    density.  Pages whose score is at least ``threshold`` are returned as
    one-based page numbers.
    """
    raw_pages = extract_text_from_first_pages(pdf_path, max_pages=max_pages)

    analyses: list[PageAnalysis] = []
    for raw_page in raw_pages:
        page_text = str(raw_page["text"])
        page_score, page_signals = score_page(page_text)
        analyses.append(
            PageAnalysis(
                page_number=int(raw_page["page_number"]),
                text=page_text,
                score=page_score,
                signals=page_signals,
            )
        )

    toc_pages = [analysis.page_number for analysis in analyses if analysis.score >= threshold]
    confidence = max((analysis.score for analysis in analyses), default=0.0)

    all_signals = [
        signal
        for analysis in analyses
        if analysis.score >= threshold
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

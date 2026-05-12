"""Data models for PDF TOC detection."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PageAnalysis:
    """Analysis result for a single PDF page."""

    page_number: int
    text: str
    score: float
    signals: list[str] = field(default_factory=list)


@dataclass
class TocDetectionResult:
    """Result returned by :func:`docpipeline.parsing.pdf.toc.detect_toc`."""

    has_toc: bool
    confidence: float
    toc_pages: list[int]
    reason: str

    def to_dict(self) -> dict[str, bool | float | list[int] | str]:
        """Serialise the result to a plain dictionary."""
        return {
            "has_toc": self.has_toc,
            "confidence": round(self.confidence, 4),
            "toc_pages": self.toc_pages,
            "reason": self.reason,
        }

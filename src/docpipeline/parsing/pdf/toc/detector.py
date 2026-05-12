"""
TODO-TOC-001 — Détection heuristique de table des matières dans un PDF.

ZERO LLM — scoring basé sur 5 signaux textuels.
Chaque page reçoit un score [0, 1] ; la page qui dépasse le seuil est retenue.

Signaux et poids :
  - Mot-clé TOC (sommaire, table des matières…)  : 0.40
  - Lignes pointillées (≥ 3 occurrences)          : 0.30
  - Lignes terminant par un nombre (≥ 3)          : 0.20
  - Numérotation hiérarchique (≥ 3 entrées)       : 0.20
  - Densité élevée de lignes courtes              : 0.10
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF


# ── Seuils et poids (constants exposées pour override) ───────────────────────

WEIGHT_KEYWORD: float = 0.40
WEIGHT_DOTTED_LEADERS: float = 0.30
WEIGHT_LINES_WITH_NUMBER: float = 0.20
WEIGHT_HIERARCHICAL: float = 0.20
WEIGHT_SHORT_LINE_DENSITY: float = 0.10

MIN_OCCURRENCES: int = 3
SHORT_LINE_DENSITY_THRESHOLD: float = 0.60
DEFAULT_MAX_PAGES: int = 5
DEFAULT_THRESHOLD: float = 0.50

_TOC_KEYWORDS: list[str] = [
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


# ── Contrats de sortie ────────────────────────────────────────────────────────

@dataclass
class TocDetectionResult:
    """Résultat de la détection heuristique d'une table des matières."""

    has_toc: bool
    confidence: float
    toc_pages: list[int]
    reason: str

    def to_dict(self) -> dict:
        """Sérialiser le résultat en dictionnaire Python."""
        return {
            "has_toc": self.has_toc,
            "confidence": round(self.confidence, 4),
            "toc_pages": self.toc_pages,
            "reason": self.reason,
        }


@dataclass
class _PageAnalysis:
    page_number: int
    score: float
    signals: list[str] = field(default_factory=list)


# ── Analyse textuelle (ZERO LLM) ─────────────────────────────────────────────

def _has_keyword(text: str) -> bool:
    """Détecter un mot-clé de table des matières dans un texte normalisé."""
    normalized = text.lower()
    return any(kw in normalized for kw in _TOC_KEYWORDS)


def _score_page(text: str) -> tuple[float, list[str]]:
    """Calculer un score heuristique [0, 1] et les signaux détectés pour une page."""
    raw_score: float = 0.0
    signals: list[str] = []

    if _has_keyword(text):
        raw_score += WEIGHT_KEYWORD
        signals.append("TOC keyword detected")

    dotted = _DOTTED_LEADER_RE.findall(text)
    if len(dotted) >= MIN_OCCURRENCES:
        raw_score += WEIGHT_DOTTED_LEADERS
        signals.append(f"Dotted leader patterns found ({len(dotted)} occurrences)")

    numbered = _LINE_ENDING_WITH_NUMBER_RE.findall(text)
    if len(numbered) >= MIN_OCCURRENCES:
        raw_score += WEIGHT_LINES_WITH_NUMBER
        signals.append(f"Multiple lines ending with page numbers ({len(numbered)} occurrences)")

    hierarchical = _HIERARCHICAL_RE.findall(text)
    if len(hierarchical) >= MIN_OCCURRENCES:
        raw_score += WEIGHT_HIERARCHICAL
        signals.append(f"Hierarchical numbering structure detected ({len(hierarchical)} entries)")

    lines = [ln for ln in text.splitlines() if ln.strip()]
    if lines:
        density = sum(1 for ln in lines if len(ln.strip()) <= _SHORT_LINE_MAX_LEN) / len(lines)
        if density > SHORT_LINE_DENSITY_THRESHOLD:
            raw_score += WEIGHT_SHORT_LINE_DENSITY
            signals.append(f"High short-line density ({density:.0%})")

    return min(raw_score, 1.0), signals


# ── Point d'entrée public ─────────────────────────────────────────────────────

def detect_toc(
    pdf_path: str | Path,
    max_pages: int = DEFAULT_MAX_PAGES,
    threshold: float = DEFAULT_THRESHOLD,
) -> TocDetectionResult:
    """
    TODO-TOC-001 — Détecter si un PDF contient une table des matières.

    Inspecte uniquement les `max_pages` premières pages. Chaque page reçoit
    un score heuristique ; une page est retenue comme page de TOC si son score
    ≥ `threshold`. La confiance finale est le score maximum trouvé.

    Input  : chemin PDF, nombre max de pages, seuil de confiance
    Output : TocDetectionResult (has_toc, confidence, toc_pages, reason)

    ZERO LLM — 5 signaux textuels pondérés, aucun modèle externe.
    """
    with fitz.open(str(pdf_path)) as doc:
        analyses: list[_PageAnalysis] = []
        for i in range(min(max_pages, doc.page_count)):
            page_text = doc[i].get_text("text")
            page_score, page_signals = _score_page(page_text)
            analyses.append(_PageAnalysis(
                page_number=i + 1,
                score=page_score,
                signals=page_signals,
            ))

    toc_pages = [a.page_number for a in analyses if a.score >= threshold]
    confidence = max((a.score for a in analyses), default=0.0)

    all_signals = [sig for a in analyses if a.score >= threshold for sig in a.signals]
    unique_signals = list(dict.fromkeys(all_signals))
    reason = "; ".join(unique_signals) if unique_signals else "No significant TOC signals found"

    return TocDetectionResult(
        has_toc=bool(toc_pages),
        confidence=round(confidence, 4),
        toc_pages=toc_pages,
        reason=reason,
    )

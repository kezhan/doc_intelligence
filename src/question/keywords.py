"""§2.3 — High-signal anchor keywords.

Codes, identifiants, références réglementaires : trop importants pour être
dilués dans la moyenne d'un embedding. On les route vers l'index lexical
(BM25) en parallèle de l'index dense.
"""

from __future__ import annotations

import re

_PATTERNS = [
    r"\b[A-Z]{2,}-?\d+(?:[-/]\d+)*\b",   # L131-1, ISO-9001, RC-2024
    r"\b[A-Z]{3,}\b",                     # GDPR, RCP, SLA
    r"\b\d{4,}\b",                        # années, identifiants numériques
]


def extract_anchor_keywords(question: str) -> list[str]:
    """Extrait codes / acronymes / identifiants à fort signal lexical."""
    keywords: list[str] = []
    for pattern in _PATTERNS:
        keywords.extend(re.findall(pattern, question))
    # dédupliquer en préservant l'ordre d'apparition
    seen: set[str] = set()
    out: list[str] = []
    for k in keywords:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out

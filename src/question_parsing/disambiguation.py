"""§3.3 — Disambiguation cues.

Quand l'utilisateur dit « not the deductible », il signale que deux concepts
proches vont apparaître dans les passages retrouvés et qu'il n'en veut qu'un.
Cette consigne va dans le prompt de génération, JAMAIS au retriever.
"""

from __future__ import annotations

import re

_PATTERNS = [
    r"not\s+the\s+(\w+)",
    r"instead\s+of\s+the\s+(\w+)",
    r"(?:don't|do not)\s+confuse\s+(?:it\s+)?with\s+(?:the\s+)?(\w+)",
    r"as\s+opposed\s+to\s+the\s+(\w+)",
    r"excluding\s+the\s+(\w+)",
    # FR
    r"pas\s+(?:la|le|les)\s+(\w+)",
    r"à\s+ne\s+pas\s+confondre\s+avec\s+(?:la|le|les)\s+(\w+)",
]


def extract_disambiguation(question: str) -> tuple[str | None, list[str]]:
    """Renvoie (instruction pour le générateur, liste des distractors)."""
    distractors: list[str] = []
    for pattern in _PATTERNS:
        distractors.extend(re.findall(pattern, question, re.IGNORECASE))

    distractors = list(dict.fromkeys(distractors))  # dédupe en préservant l'ordre

    if not distractors:
        return None, []

    instruction = (
        f"The user is asking about the main concept, NOT about: "
        f"{', '.join(distractors)}. Both may appear in the retrieved passages "
        f"— extract only the main one."
    )
    return instruction, distractors

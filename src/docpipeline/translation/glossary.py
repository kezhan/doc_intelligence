"""
TODO-013 — Business term detection in source text
TODO-014 — Business glossary construction and management
TODO-015 — Decision: translate vs keep-as-is
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ── TODO-014 — Glossary data model ───────────────────────────────────────────

@dataclass
class GlossaryEntry:
    term: str
    source_language: str
    translations: dict[str, list[str]]   # target_lang → [candidate1, candidate2, ...]
    context: str = ""                     # domain / usage note
    keep_as_is: bool = False             # never translate this term

    def candidates(self, target_lang: str) -> list[str]:
        return self.translations.get(target_lang, [])


class Glossary:
    """
    TODO-014 — Manages a structured business glossary.

    Backed by a JSON file:
    [
      {
        "term": "IA", "source_language": "fr",
        "translations": {"en": ["Individual Accident"]},
        "context": "insurance", "keep_as_is": false
      },
      ...
    ]
    """

    def __init__(self, entries: list[GlossaryEntry] | None = None) -> None:
        self._entries: dict[str, GlossaryEntry] = {}
        for entry in (entries or []):
            self.add(entry)

    def add(self, entry: GlossaryEntry) -> None:
        self._entries[entry.term.lower()] = entry

    def get(self, term: str) -> GlossaryEntry | None:
        return self._entries.get(term.lower())

    def __len__(self) -> int:
        return len(self._entries)

    @classmethod
    def from_json(cls, path: str | Path) -> "Glossary":
        data: list[dict[str, Any]] = json.loads(Path(path).read_text(encoding="utf-8"))
        entries = [
            GlossaryEntry(
                term=d["term"],
                source_language=d["source_language"],
                translations=d.get("translations", {}),
                context=d.get("context", ""),
                keep_as_is=d.get("keep_as_is", False),
            )
            for d in data
        ]
        return cls(entries)

    def to_json(self, path: str | Path) -> None:
        data = [
            {
                "term": e.term,
                "source_language": e.source_language,
                "translations": e.translations,
                "context": e.context,
                "keep_as_is": e.keep_as_is,
            }
            for e in self._entries.values()
        ]
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def prompt_context(self, detected_terms: list["DetectedTerm"], target_lang: str) -> str:
        """Build the glossary injection string for LLM prompts."""
        lines: list[str] = []
        for dt in detected_terms:
            entry = self.get(dt.term)
            if entry is None:
                continue
            if entry.keep_as_is:
                lines.append(f'- "{dt.term}": keep as-is (do not translate)')
            else:
                candidates = entry.candidates(target_lang)
                if candidates:
                    joined = " / ".join(f'"{c}"' for c in candidates)
                    lines.append(f'- "{dt.term}": preferred translations: {joined}')
        return "\n".join(lines)


# ── TODO-013 — Business term detection ───────────────────────────────────────

@dataclass
class DetectedTerm:
    term: str
    start: int
    end: int
    candidates: list[str] = field(default_factory=list)


def detect_business_terms(
    text: str,
    glossary: Glossary,
) -> list[DetectedTerm]:
    """
    TODO-013 — Detect glossary terms in a source text.

    Input : raw text + populated Glossary
    Output: list of DetectedTerm with position + translation candidates
    """
    found: list[DetectedTerm] = []
    text_lower = text.lower()

    for term_key, entry in glossary._entries.items():
        for match in re.finditer(re.escape(term_key), text_lower):
            # Validate word boundary
            start, end = match.start(), match.end()
            before = text_lower[start - 1] if start > 0 else " "
            after = text_lower[end] if end < len(text_lower) else " "
            if before.isalpha() or after.isalpha():
                continue
            found.append(DetectedTerm(
                term=text[start:end],
                start=start,
                end=end,
                candidates=list(entry.translations.values())[0] if entry.translations else [],
            ))

    found.sort(key=lambda d: d.start)
    return found


# ── TODO-015 — Translate vs keep-as-is decision ───────────────────────────────

@dataclass
class TranslateDecision:
    action: str       # "translate" | "keep_as_is"
    reason: str
    detected_language: str | None = None


def decide_translate_or_keep(
    term: str,
    *,
    context: str = "",
    glossary: Glossary | None = None,
    target_language: str = "en",
) -> TranslateDecision:
    """
    TODO-015 — Decide whether to translate or preserve a term.

    Input : term + context string + optional glossary
    Output: TranslateDecision
    """
    # Glossary says keep-as-is
    if glossary:
        entry = glossary.get(term)
        if entry and entry.keep_as_is:
            return TranslateDecision("keep_as_is", "glossary_override")

    detected = _detect_language(term)

    # Term is already in the target language
    if detected == target_language:
        return TranslateDecision(
            "keep_as_is",
            f"term_already_in_target_language ({target_language})",
            detected_language=detected,
        )

    # Proper noun / acronym heuristic: all-caps short token → keep
    if term.isupper() and len(term) <= 5 and (not glossary or not glossary.get(term)):
        return TranslateDecision(
            "keep_as_is",
            "unknown_acronym_keep_safe",
            detected_language=detected,
        )

    return TranslateDecision("translate", "default_translate", detected_language=detected)


# ── helpers ───────────────────────────────────────────────────────────────────

_EN_STOPWORDS = frozenset(
    {"the", "and", "for", "with", "this", "that", "from", "have", "are", "was"}
)
_FR_STOPWORDS = frozenset(
    {"le", "la", "les", "un", "une", "des", "est", "dans", "avec", "pour", "que", "qui"}
)


def _detect_language(text: str) -> str | None:
    """Fast heuristic language detection (no external dependency)."""
    words = re.findall(r"\b\w+\b", text.lower())
    if not words:
        return None
    en_hits = sum(1 for w in words if w in _EN_STOPWORDS)
    fr_hits = sum(1 for w in words if w in _FR_STOPWORDS)
    if en_hits > fr_hits:
        return "en"
    if fr_hits > en_hits:
        return "fr"
    return None

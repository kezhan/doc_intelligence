"""
request_js.py — TranslationRequest + parse_translation_request (Step 3
build order Tome 2).

Cf. CLAUDE_tome2_translation.md §1.2. Brique "question" du pipeline de
traduction : transforme un message libre utilisateur en un schema Pydantic
declaratif que les briques en aval (scope, translate_chunks, distribute,
render) consomment.

    "Translate this contract into formal English, skip the annexes,
     and use 'deductible' for 'franchise'."
        |
        v
    TranslationRequest(
        target_language="en",
        style="formal",
        scope=TranslationScope(exclude_sections=["Annexes"]),
        glossary_additions=[GlossaryEntry(source="franchise", target="deductible")],
    )

Le spec prevoit un appel LLM analogue a `parse_question` du Tome 1. Cette
implementation est volontairement deterministe (regex + lookup), zero LLM,
pour debloquer le pipeline quand aucune cle API n'est disponible. Quand la
voie LLM sera necessaire, brancher dans un `parse_translation_request_llm`
et garder ce parser comme fallback.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from docpipeline.translation.scope_js import TranslationScope


# ----- Schemas ---------------------------------------------------------------

class GlossaryEntry(BaseModel):
    """Une paire source -> target pour le glossaire ad-hoc."""

    source: str
    target: str


Style = Literal["formal", "casual", "technical", "default"]


class TranslationRequest(BaseModel):
    """Specification structuree d'une demande de traduction.

    Sortie de `parse_translation_request`. Consommee par scope, translate_chunks,
    distribute, render.
    """

    target_language: str                         # ISO 639-1 court : "en", "fr", "de"
    source_language: str | None = None           # None = auto-detect
    scope: TranslationScope | None = None
    style: Style = "default"
    glossary_additions: list[GlossaryEntry] = []


# ----- Tables de lookup ------------------------------------------------------

# Termes en plusieurs langues -> code ISO 639-1.
# On garde une table compacte avec les langues les plus probables dans le
# corpus assurance/legal Kezhan (FR, EN, DE, ES, IT, PT, NL, ZH, JA).
_LANG_LOOKUP: dict[str, str] = {
    # english
    "english": "en", "anglais": "en", "inglese": "en", "ingles": "en",
    "englisch": "en", "engels": "en", "en": "en",
    # french
    "french": "fr", "francais": "fr", "français": "fr", "francese": "fr",
    "frances": "fr", "französisch": "fr", "frans": "fr", "fr": "fr",
    # german
    "german": "de", "allemand": "de", "tedesco": "de", "aleman": "de",
    "alemán": "de", "deutsch": "de", "deutsche": "de", "duits": "de", "de": "de",
    # spanish
    "spanish": "es", "espagnol": "es", "spagnolo": "es", "espanol": "es",
    "español": "es", "spanisch": "es", "spaans": "es", "es": "es",
    # italian
    "italian": "it", "italien": "it", "italiano": "it", "italienisch": "it",
    "italiaans": "it", "it": "it",
    # portuguese
    "portuguese": "pt", "portugais": "pt", "portoghese": "pt",
    "portugues": "pt", "português": "pt", "pt": "pt",
    # dutch
    "dutch": "nl", "neerlandais": "nl", "néerlandais": "nl",
    "olandese": "nl", "neerlandes": "nl", "nl": "nl",
    # chinese
    "chinese": "zh", "chinois": "zh", "cinese": "zh", "chino": "zh",
    "chinesisch": "zh", "chinees": "zh", "zh": "zh", "中文": "zh",
    # japanese
    "japanese": "ja", "japonais": "ja", "giapponese": "ja", "japones": "ja",
    "japanisch": "ja", "japans": "ja", "ja": "ja", "日本語": "ja",
}

_STYLE_KEYWORDS: dict[str, Style] = {
    "formal": "formal", "formel": "formal", "formelle": "formal",
    "soutenu": "formal", "professional": "formal", "professionnel": "formal",
    "casual": "casual", "informel": "casual", "informal": "casual",
    "decontracte": "casual", "décontracté": "casual", "friendly": "casual",
    "technical": "technical", "technique": "technical",
    "scientifique": "technical", "scientific": "technical",
}

# Marqueurs de scope dans la phrase
_EXCLUDE_PATTERNS = [
    r"\b(?:skip|except|without|excluding|exclude|sauf|sans|excepte|excepté|hors|hormis)\s+(?:the\s+|les\s+|le\s+|la\s+|l[''])?([\w\s,&-]+?)(?=[.!,;]|$|\s+(?:and|et|but|but)\s+)",
    r"\b(?:do not|don'?t|ne pas|ne)\s+translate\s+(?:the\s+|les\s+|le\s+|la\s+)?([\w\s,&-]+?)(?=[.!,;]|$)",
]
_INCLUDE_PATTERNS = [
    r"\b(?:only|just|seulement|uniquement)\s+(?:translate\s+)?(?:the\s+|les\s+|le\s+|la\s+)?([\w\s,&-]+?)(?=[.!,;]|$|\s+(?:and|et)\s+)",
]
_PAGE_RANGE_PATTERNS = [
    r"\bpages?\s+(\d+)\s*(?:to|-|–|a|à|jusqu['']?a|jusqu['']?à)\s*(\d+)\b",
    r"\bfrom\s+page\s+(\d+)\s+to\s+(?:page\s+)?(\d+)\b",
    r"\bde\s+la\s+page\s+(\d+)\s+(?:a|à|jusqu['']?a|jusqu['']?à)\s+(?:la\s+page\s+)?(\d+)\b",
]
# "use 'X' for 'Y'", "translate X as Y", "X = Y", "X -> Y"
_GLOSSARY_PATTERNS = [
    r"use\s+['\"]([^'\"]+)['\"]\s+for\s+['\"]([^'\"]+)['\"]",
    r"translate\s+['\"]([^'\"]+)['\"]\s+as\s+['\"]([^'\"]+)['\"]",
    r"traduire\s+['\"]([^'\"]+)['\"]\s+(?:par|en)\s+['\"]([^'\"]+)['\"]",
    r"['\"]([^'\"]+)['\"]\s*(?:->|=>|:=|=)\s*['\"]([^'\"]+)['\"]",
]


def _norm(s: str) -> str:
    """Lowercase, ascii-fold, strip."""
    import unicodedata
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.casefold().strip()


def _match_language(message: str) -> str | None:
    """Cherche dans le message un mot listant une langue. Retourne le code ISO."""
    msg_norm = _norm(message)
    # Tokenisation grossiere pour matcher les noms entiers (eviter "en" dans "and")
    tokens = re.findall(r"\b[\w一-鿿]+\b", msg_norm)
    # On scanne les patterns "into X", "to X", "in X", "en X"
    into_pattern = re.compile(
        r"\b(?:into|to|in|ins|im|en|vers|towards?|à|a|al)\s+([\w一-鿿]+)"
    )
    candidates = [m.group(1) for m in into_pattern.finditer(msg_norm)]
    for cand in candidates:
        if cand in _LANG_LOOKUP:
            return _LANG_LOOKUP[cand]
    # Sinon, on cherche n'importe quel token connu (sauf les codes 2-lettres
    # qui sont trop ambigus pour un match isole)
    for tok in tokens:
        if len(tok) >= 3 and tok in _LANG_LOOKUP:
            return _LANG_LOOKUP[tok]
    return None


def _match_source_language(message: str) -> str | None:
    """Cherche 'from X' / 'depuis X' / 'de X'."""
    msg_norm = _norm(message)
    pattern = re.compile(r"\b(?:from|depuis|du|de)\s+(?:the\s+)?([a-z]+)")
    for m in pattern.finditer(msg_norm):
        cand = m.group(1)
        if cand in _LANG_LOOKUP:
            return _LANG_LOOKUP[cand]
    return None


def _match_style(message: str) -> Style:
    msg_norm = _norm(message)
    tokens = set(re.findall(r"\b\w+\b", msg_norm))
    for kw, style in _STYLE_KEYWORDS.items():
        if kw in tokens:
            return style
    return "default"


def _match_sections(message: str, patterns: list[str]) -> list[str]:
    """Extrait des noms de sections via une liste de patterns regex."""
    out: list[str] = []
    msg = message  # on garde la casse pour restituer "Annexes" et pas "annexes"
    for pat in patterns:
        for m in re.finditer(pat, msg, flags=re.IGNORECASE):
            section = m.group(1).strip().rstrip(",.;").strip()
            if section and section.lower() not in {s.lower() for s in out}:
                # Capitaliser la 1ere lettre pour homogeneite
                out.append(section[0].upper() + section[1:] if section else section)
    return out


def _match_page_range(message: str) -> tuple[int, int] | None:
    for pat in _PAGE_RANGE_PATTERNS:
        m = re.search(pat, message, flags=re.IGNORECASE)
        if m:
            return (int(m.group(1)), int(m.group(2)))
    return None


def _match_glossary(message: str) -> list[GlossaryEntry]:
    """Extrait les paires source/target. Convention 'use X for Y' = source=Y, target=X
    (le user dit 'use le mot Y pour la source X')."""
    out: list[GlossaryEntry] = []
    seen: set[tuple[str, str]] = set()
    # 'use X for Y' -> source=Y, target=X (le X est le terme cible a utiliser)
    for m in re.finditer(_GLOSSARY_PATTERNS[0], message, flags=re.IGNORECASE):
        target, source = m.group(1).strip(), m.group(2).strip()
        key = (source.lower(), target.lower())
        if key not in seen:
            out.append(GlossaryEntry(source=source, target=target))
            seen.add(key)
    # 'translate X as Y' / 'traduire X par Y' -> source=X, target=Y
    for pat in _GLOSSARY_PATTERNS[1:3]:
        for m in re.finditer(pat, message, flags=re.IGNORECASE):
            source, target = m.group(1).strip(), m.group(2).strip()
            key = (source.lower(), target.lower())
            if key not in seen:
                out.append(GlossaryEntry(source=source, target=target))
                seen.add(key)
    # 'X -> Y' -> source=X, target=Y
    for m in re.finditer(_GLOSSARY_PATTERNS[3], message, flags=re.IGNORECASE):
        source, target = m.group(1).strip(), m.group(2).strip()
        key = (source.lower(), target.lower())
        if key not in seen:
            out.append(GlossaryEntry(source=source, target=target))
            seen.add(key)
    return out


# ----- Public API ------------------------------------------------------------

def parse_translation_request(message: str) -> TranslationRequest:
    """Parse un message libre en TranslationRequest. Deterministe, zero LLM.

    Args:
        message : phrase libre de l'utilisateur, par exemple
                  "Translate this contract into formal English, skip the
                  annexes, and use 'deductible' for 'franchise'."

    Returns:
        TranslationRequest. Si la langue cible n'a pas pu etre detectee,
        leve ValueError.

    Raises:
        ValueError : aucune langue cible identifiable. Pour une dispatch
                     plus tolerante, wrapper en amont avec un default.
    """
    if not message or not message.strip():
        raise ValueError("Message vide : impossible de deduire une langue cible.")

    target_language = _match_language(message)
    if target_language is None:
        raise ValueError(
            f"Aucune langue cible reconnue dans : {message!r}. "
            "Specifier une langue (ex. 'into English' ou 'en francais')."
        )
    source_language = _match_source_language(message)
    style = _match_style(message)
    exclude_sections = _match_sections(message, _EXCLUDE_PATTERNS)
    include_sections = _match_sections(message, _INCLUDE_PATTERNS)
    page_range = _match_page_range(message)
    glossary_additions = _match_glossary(message)

    scope: TranslationScope | None = None
    if exclude_sections or include_sections or page_range is not None:
        scope = TranslationScope(
            page_range=page_range,
            include_sections=include_sections or None,
            exclude_sections=exclude_sections or None,
        )

    return TranslationRequest(
        target_language=target_language,
        source_language=source_language,
        scope=scope,
        style=style,
        glossary_additions=glossary_additions,
    )


if __name__ == "__main__":
    import json
    samples = [
        "Translate this contract into formal English, skip the annexes, "
        "and use 'deductible' for 'franchise'.",
        "Traduire ce document en allemand, style technique.",
        "Translate pages 3 to 15 into Spanish, only the Body section.",
        "Translate this from French to English.",
    ]
    for s in samples:
        try:
            req = parse_translation_request(s)
            print(f"IN : {s}")
            print(f"OUT: {req.model_dump_json(indent=2)}")
        except ValueError as e:
            print(f"IN : {s}\nERR: {e}")
        print()

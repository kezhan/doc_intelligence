"""
question_parsing.py — Brique 2 : parser une question utilisateur en JSON.

Référence : chapitre « Understanding the Question Before Searching » (4ème onglet
du Google Doc Faseya partagé par Kezhan).

Idée centrale : une question utilisateur n'est pas un seul input. C'est la matière
première pour DEUX préparations distinctes :

  1. RetrievalQuery  : ce qui sert à CHERCHER dans les documents
                       (query nettoyée, anchor keywords, hints structurels)
  2. GenerationBrief : ce qui sert à FORMULER la réponse
                       (question originale, format attendu, désambiguïsation)

Point d'entrée unique : `parse_question(question)` retourne un `ParsedQuestion`
sérialisable en JSON, directement consommable par la brique 3 (Retrieval).

Approche : regex / heuristique uniquement, pas de LLM.
  (Règle d'équipe : LLM réservé à translation / summarization / Excel SQL agent —
  jamais dans parsing, classification, retrieval. Cf. CLAUDE.md du repo.)
  Pas de classe, fonctions pures + dataclass.

Liens avec parse_pdf.py : les hints produits ici (`page_hint`, `layout_hint`,
`section_hint`) matchent directement les flags du `page_df` produit par
`parse_pdf` (`page_num`, `has_vector_table`, `has_full_page_image`). C'est
l'infrastructure de routage pour la brique 3 Retrieval.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Optional


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 1. CONSTANTES — patterns regex                                             ║
# ╚════════════════════════════════════════════════════════════════════════════╝

# ─── Page ─────────────────────────────────────────────────────────────────────
_PAGE_PATTERNS = (
    re.compile(r"\bpage\s*n?[°o]?\s*(\d+)",     re.IGNORECASE),
    re.compile(r"\bp\.?\s*(\d+)\b",             re.IGNORECASE),
    re.compile(r"\bon\s+page\s+(\d+)",          re.IGNORECASE),
    re.compile(r"\bà\s+la\s+page\s+(\d+)",      re.IGNORECASE),
)

# ─── Section ──────────────────────────────────────────────────────────────────
_SECTION_PATTERNS = (
    re.compile(
        r"section\s+(?:called|nommée|appelée|nommé|appelé|named)\s+"
        r"['\"]?([\w\sàâéèêëïîôùûüç-]+?)['\"]?(?=[\.,;]|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:dans\s+la|in\s+the)\s+section\s+"
        r"['\"]?([\w\sàâéèêëïîôùûüç-]+?)['\"]?(?=[\.,;]|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bsection\s+['\"]([\w\s\-àâéèêëïîôùûüç]+?)['\"]",
        re.IGNORECASE,
    ),
)

# ─── Layout ───────────────────────────────────────────────────────────────────
_LAYOUT_KEYWORDS = {
    "table":  ("table", "tableau", "grille"),
    "image":  ("image", "figure", "diagramme", "diagram", "schéma", "schema", "photo"),
    "header": ("header", "en-tête", "entête", "haut de page"),
    "footer": ("footer", "pied de page", "bas de page"),
}

# ─── Document / scope ─────────────────────────────────────────────────────────
_DOCUMENT_PATTERNS = (
    re.compile(
        r"(?:la\s+)?(?:dernière|latest)\s+version"
        r"\s+(?:du\s+)?(?:contrat|document|policy|polic[eé])?",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:dans|in)\s+(?:le|the)\s+"
        r"(?:contrat|document|polic[eé]|policy)\s+([\w\-]+)",
        re.IGNORECASE,
    ),
)

# ─── Anchor keywords (codes, IDs, références juridiques, acronymes) ──────────
_ANCHOR_PATTERNS = (
    re.compile(r"\b[A-Z]+\d+(?:[-./]\d+)+\b"),       # L131-1, ISO-9001-2015
    re.compile(r"\b[A-Z]{2,}-\d+(?:[-/]\d+)*\b"),    # RC-2024, GDPR-001
    re.compile(r"\b[A-Z]{3,}\b"),                    # GDPR, RCP, SLA, NDA
    re.compile(r"\b\d{4,}\b"),                       # années, identifiants
    re.compile(r"\b[lL]\.?\s?\d+[-]\d+\b"),          # L131-1, L. 131-1 (français juridique)
    re.compile(r"\b(?:art\.?|article)\s+\d+(?:[-.]\d+)*\b", re.IGNORECASE),  # article 1234
)

# ─── Format constraint (sortie attendue) ──────────────────────────────────────
_FORMAT_RULES = (
    (r"\b(?:yyyy[-/]mm[-/]dd|iso\s*8601|iso\s*date)\b", "ISO 8601 date (YYYY-MM-DD)"),
    (r"\bjson\b",                                       "valid JSON"),
    (r"\b(?:in\s+euros?|en\s+euros?|€)\b",              "numeric value in EUR"),
    (r"\b(?:in\s+dollars?|en\s+dollars?|usd|\$)\b",     "numeric value in USD"),
    (r"\bas\s+a\s+number\b",                            "numeric value"),
    (r"\b(?:in\s+one\s+sentence|en\s+une\s+phrase)\b",  "single sentence, no preamble"),
    (r"\b(?:bullet|liste|list)\b",                      "bullet list"),
    (r"\b(?:yes\s*/\s*no|oui\s*/\s*non|boolean)\b",     "boolean (yes/no)"),
    (r"\b(?:percentage|pourcentage|%)\b",               "percentage"),
)

# ─── Disambiguation (« X, not Y », « instead of Y », ... ) ────────────────────
_DISAMBIG_PATTERNS = (
    re.compile(r"\bnot\s+(?:the\s+)?([\w\sàâéèêëïîôùûüç-]{2,30}?)(?=[\.,;]|$)", re.IGNORECASE),
    re.compile(r"\bpas\s+(?:la\s+|le\s+|les\s+)?([\w\sàâéèêëïîôùûüç-]{2,30}?)(?=[\.,;]|$)", re.IGNORECASE),
    re.compile(r"\binstead\s+of\s+(?:the\s+)?([\w\sàâéèêëïîôùûüç-]{2,30}?)(?=[\.,;]|$)", re.IGNORECASE),
    re.compile(r"(?:don['’]t|do\s+not)\s+confuse\s+(?:it\s+)?with\s+(?:the\s+)?([\w\sàâéèêëïîôùûüç-]{2,30}?)(?=[\.,;]|$)", re.IGNORECASE),
    re.compile(r"\bas\s+opposed\s+to\s+(?:the\s+)?([\w\sàâéèêëïîôùûüç-]{2,30}?)(?=[\.,;]|$)", re.IGNORECASE),
    re.compile(r"\bexcluding\s+(?:the\s+)?([\w\sàâéèêëïîôùûüç-]{2,30}?)(?=[\.,;]|$)", re.IGNORECASE),
)

# ─── Intent (heuristique simple sur les mots-clés) ────────────────────────────
# ORDRE = priorité : on vérifie compare/aggregate/conditional d'abord (signaux
# spécifiques), puis extract (« what is », « quel est »…), et yes_no en dernier
# (le « is » de yes/no est trop large et matche aussi « what IS the … »).
_INTENT_KEYWORDS = (
    ("compare",     ("compare", "comparer", "consistent", "cohérent", " vs ", "versus")),
    ("aggregate",   ("list all", "lister tout", "tous les", "all the", "ensemble des", "rank", "classer")),
    ("conditional", ("if so", "si oui", "and if", "et si")),
    ("extract",     ("what is", "quel est", "quelle est", "find", "trouve", "donne-moi", "give me")),
    ("yes_no",      ("does ", " is ", "est-ce que", "y a-t-il", "has ", "have you", "are there")),
)


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 2. DATACLASSES — sortie publique                                           ║
# ╚════════════════════════════════════════════════════════════════════════════╝

@dataclass
class StructuralHints:
    """Indices structurels extraits d'une question (page / section / layout / doc)."""
    section_hint:   Optional[str] = None
    page_hint:      Optional[int] = None
    layout_hint:    Optional[str] = None     # "table" | "image" | "header" | "footer"
    document_hint:  Optional[str] = None
    raw_signals:    list[str]     = field(default_factory=list)


@dataclass
class Disambiguation:
    """Patterns « X, not Y » détectés — orientent la génération, pas le retrieval."""
    distractors:    list[str] = field(default_factory=list)
    instruction:    Optional[str] = None     # texte injectable dans un prompt LLM
    raw_signals:    list[str] = field(default_factory=list)


@dataclass
class ParsedQuestion:
    """
    Représentation structurée d'une question utilisateur. Sérialisable en JSON via
    `dataclasses.asdict(parsed) → json.dumps(...)`. Consommée directement par la
    brique 3 Retrieval.
    """
    original_question:   str
    main_query:          str                       # version nettoyée (strip, espaces)
    structural_hints:    StructuralHints
    anchor_keywords:     list[str]                 # codes / IDs / acronymes pour BM25
    format_constraint:   Optional[str]             # YYYY-MM-DD / JSON / bullet list...
    disambiguation:      Disambiguation
    intent:              str                       # extract / compare / aggregate / ...
    raw_signals:         list[str]                 # traçabilité globale
    parser_version:      str = "1.0.0"


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 3. EXTRACTORS — un par champ                                               ║
# ╚════════════════════════════════════════════════════════════════════════════╝

# ─── 3.1 Hints structurels (page / section / layout / document) ──────────────

def _extract_page(question: str) -> tuple[Optional[int], Optional[str]]:
    for pat in _PAGE_PATTERNS:
        m = pat.search(question)
        if m:
            try:
                return int(m.group(1)), f"regex_page:{m.group(0)!r}"
            except (ValueError, IndexError):
                continue
    return None, None


def _extract_section(question: str) -> tuple[Optional[str], Optional[str]]:
    for pat in _SECTION_PATTERNS:
        m = pat.search(question)
        if m:
            name = m.group(1).strip().rstrip(".,;:")
            if name:
                return name, f"regex_section:{m.group(0)!r}"
    return None, None


def _extract_layout(question: str) -> tuple[Optional[str], Optional[str]]:
    q_lower = question.lower()
    for layout_type, keywords in _LAYOUT_KEYWORDS.items():
        for kw in keywords:
            if re.search(rf"\b{re.escape(kw)}\b", q_lower):
                return layout_type, f"regex_layout:{kw}→{layout_type}"
    return None, None


def _extract_document(question: str) -> tuple[Optional[str], Optional[str]]:
    for pat in _DOCUMENT_PATTERNS:
        m = pat.search(question)
        if m:
            matched = m.group(0).strip()
            return matched, f"regex_document:{matched!r}"
    return None, None


def extract_hints(question: str) -> StructuralHints:
    """
    Extraire les indices structurels d'une question utilisateur.

    Patterns couverts (regex déterministe, sans LLM) :
      - page_hint    : "page 1", "p. 12", "à la page 47", "on page X"
      - section_hint : "dans la section X", "section called X", "in the section X"
      - layout_hint  : "table" / "tableau" → table ; "image" / "figure" → image ;
                        "header" / "en-tête" → header ; "footer" / "pied" → footer
      - document_hint: "latest version", "dernière version", "dans le contrat X"
    """
    if not question:
        return StructuralHints()

    page,    sig_page    = _extract_page(question)
    section, sig_section = _extract_section(question)
    layout,  sig_layout  = _extract_layout(question)
    doc,     sig_doc     = _extract_document(question)

    return StructuralHints(
        page_hint     = page,
        section_hint  = section,
        layout_hint   = layout,
        document_hint = doc,
        raw_signals   = [s for s in (sig_page, sig_section, sig_layout, sig_doc) if s],
    )


# ─── 3.2 Anchor keywords (codes, IDs, références juridiques) ─────────────────

# Mots fréquents en français/anglais à exclure du résultat (faux positifs sur \b[A-Z]{3,}\b)
_STOPWORDS_UPPER = frozenset({
    "THE", "AND", "FOR", "WITH", "WHAT", "WHEN", "WHERE", "WHICH", "WHO", "WHY",
    "HOW", "DOES", "ARE", "WAS", "WERE", "BUT", "NOT", "ALL", "ANY",
    "DANS", "POUR", "AVEC", "LES", "DES", "QUE", "QUI", "QUEL", "QUELLE",
    "EST", "SONT", "MAIS", "ALSO", "ABOUT", "TODO", "JSON",
})


def extract_anchor_keywords(question: str) -> tuple[list[str], list[str]]:
    """
    Extraire les tokens à fort signal qui doivent driver une recherche lexicale
    (codes, IDs, références légales, acronymes) en parallèle de l'embedding.

    Retourne (keywords, signals).
    """
    if not question:
        return [], []
    found: list[str] = []
    signals: list[str] = []
    for pat in _ANCHOR_PATTERNS:
        for m in pat.findall(question):
            tok = m.strip() if isinstance(m, str) else str(m)
            if not tok:
                continue
            if tok.upper() in _STOPWORDS_UPPER:
                continue
            if tok not in found:
                found.append(tok)
                signals.append(f"regex_anchor:{tok!r}")
    return found, signals


# ─── 3.3 Format constraint (sortie attendue par le user) ─────────────────────

def extract_format_constraint(question: str) -> tuple[Optional[str], Optional[str]]:
    """Détecter la contrainte de format de la réponse (JSON, date ISO, bullet, …)."""
    if not question:
        return None, None
    q_lower = question.lower()
    for pattern, label in _FORMAT_RULES:
        if re.search(pattern, q_lower):
            return label, f"regex_format:{pattern!r}→{label!r}"
    return None, None


# ─── 3.4 Disambiguation (« X, not Y », « instead of Y », ... ) ───────────────

def extract_disambiguation(question: str) -> Disambiguation:
    """
    Détecter les patterns de désambiguïsation (« le plafond, pas la franchise »).

    IMPORTANT (cf. chapitre Faseya) : ces signaux vont vers la GÉNÉRATION,
    JAMAIS vers le retrieval. Filtrer "deductible" au retrieval supprime la
    ligne qui contient le plafond (les deux sont souvent dans la même phrase).
    """
    if not question:
        return Disambiguation()

    distractors: list[str] = []
    raw_signals: list[str] = []
    for pat in _DISAMBIG_PATTERNS:
        for m in pat.finditer(question):
            tok = m.group(1).strip().rstrip(".,;:").lower()
            if tok and tok not in distractors and len(tok) <= 60:
                distractors.append(tok)
                raw_signals.append(f"regex_disambig:{m.group(0)!r}")

    instruction = None
    if distractors:
        instruction = (
            "L'utilisateur demande la notion principale, PAS : "
            f"{', '.join(distractors)}. Ces concepts apparaissent souvent ensemble "
            "dans les passages remontés — n'extraire que la notion principale."
        )
    return Disambiguation(
        distractors = distractors,
        instruction = instruction,
        raw_signals = raw_signals,
    )


# ─── 3.5 Intent (extract / compare / aggregate / conditional / yes_no) ───────

def classify_intent(question: str) -> str:
    """
    Classer l'intention sur des mots-clés simples. Heuristique, pas exhaustive —
    on raffinera avec les vraies questions de Kezhan.
    """
    if not question:
        return "extract"
    q_lower = question.lower()
    for intent, keywords in _INTENT_KEYWORDS:
        for kw in keywords:
            if kw in q_lower:
                return intent
    return "extract"


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 4. POINT D'ENTRÉE — parse_question                                         ║
# ╚════════════════════════════════════════════════════════════════════════════╝

def parse_question(question: str) -> ParsedQuestion:
    """
    Brique 2 : parser une question utilisateur en `ParsedQuestion` JSON-sérialisable.

    Sortie consommée par la brique 3 Retrieval, qui croisera ces hints avec les
    DataFrames produits par `parse_pdf` (page_df, line_df) pour récupérer le
    passage exact.
    """
    if question is None:
        question = ""
    main_query = " ".join(question.strip().split())

    hints      = extract_hints(question)
    keywords, kw_signals = extract_anchor_keywords(question)
    fmt, fmt_signal      = extract_format_constraint(question)
    disambig             = extract_disambiguation(question)
    intent               = classify_intent(question)

    raw_signals: list[str] = []
    raw_signals.extend(hints.raw_signals)
    raw_signals.extend(kw_signals)
    if fmt_signal:
        raw_signals.append(fmt_signal)
    raw_signals.extend(disambig.raw_signals)
    raw_signals.append(f"intent:{intent}")

    return ParsedQuestion(
        original_question = question,
        main_query        = main_query,
        structural_hints  = hints,
        anchor_keywords   = keywords,
        format_constraint = fmt,
        disambiguation    = disambig,
        intent            = intent,
        raw_signals       = raw_signals,
    )


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 5. CLI minimal                                                             ║
# ╚════════════════════════════════════════════════════════════════════════════╝

if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 2:
        print('Usage: python question_parsing.py "<question>"', file=sys.stderr)
        sys.exit(1)

    parsed = parse_question(sys.argv[1])
    print(json.dumps(asdict(parsed), indent=2, ensure_ascii=False))

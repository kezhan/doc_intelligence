"""
question_parsing.py — Brique 2 : parser une question utilisateur en JSON.

Réf : chapitre « Understanding the Question Before Searching » + design de
Kezhan dans `docs/06_question_layer.md`. Cette implémentation reprend la
philosophie « registre de briques + presets par doc_type » mais corrige
plusieurs bugs et faux positifs de la version `src/question/` initiale, et
livre une suite de tests pytest.

Point d'entrée unique :

    from docpipeline.question_parsing import parse_question
    plan = parse_question("Quelle est la prime ? Page 3.", document_type="pdf")
    # → [ { "retrieval": {...}, "generation": {...}, "_meta": {...} } ]

Garanties :
  - Toujours une **liste** de dicts (1 question simple = 1 entrée).
  - JSON sans `null` : une brique qui n'a rien trouvé ne contribue pas au JSON.
  - Connaissance métier dans les **PRESETS** par `document_type`
    (en Word pas de page_hint, en Excel pas de section_hint, etc.).

Approche : regex / heuristique, pas de LLM.
  (Règle d'équipe : LLM réservé à translation/summarization/Excel SQL agent ;
  dans la couche Question, LLM autorisé À L'INTÉRIEUR de briques ciblées
  comme rewrite/decompose/spell — non implémentées ici car LLM-only.)

Pas de classe — fonctions pures + dataclasses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 1. CONSTANTES — patterns regex                                             ║
# ╚════════════════════════════════════════════════════════════════════════════╝

# ─── Page ─────────────────────────────────────────────────────────────────────
_PAGE_PATTERNS = (
    re.compile(r"\bpage\s*n?[°o]?\s*(\d+)",  re.IGNORECASE),
    re.compile(r"\bp\.?\s*(\d+)\b",          re.IGNORECASE),
    re.compile(r"\bon\s+page\s+(\d+)",       re.IGNORECASE),
    re.compile(r"\bà\s+la\s+page\s+(\d+)",   re.IGNORECASE),
)

# ─── Section ──────────────────────────────────────────────────────────────────
# CORRECTIF du bug Kezhan « section\s+([\w\s]+?) » qui était trop greedy
# (matchait `for the flooding clause` sur « in the exclusions section for ... »).
# On distingue maintenant 4 formes :
#   1. "section called/named X"            → groupe X
#   2. "in the section X" / "dans la section X" → groupe X
#   3. "X section" (nom AVANT « section ») → groupe X
#   4. "section X"                         → groupe X (un seul mot, pas greedy)
_SECTION_PATTERNS = (
    re.compile(
        r"section\s+(?:called|named|nommée|appelée|nommé|appelé)\s+"
        r"['\"]?([\w\sàâéèêëïîôùûüç-]{2,40}?)['\"]?(?=[\.,;]|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:dans\s+(?:la|le)|in\s+the)\s+section\s+"
        r"['\"]?([\w\-àâéèêëïîôùûüç]{2,40})['\"]?(?=[\s\.,;]|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b([\w\-àâéèêëïîôùûüç]{2,40})\s+section\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bsection\s+['\"]?([\w\-àâéèêëïîôùûüç]{2,40})['\"]?(?=[\s\.,;]|$)",
        re.IGNORECASE,
    ),
)
# Mots vides à exclure du section_hint (faux positifs)
_SECTION_STOPWORDS = frozenset({
    "the", "a", "an", "le", "la", "les", "un", "une", "this", "that",
    "ce", "cette", "ces", "called", "named", "nommée", "appelée",
})

# ─── Layout ───────────────────────────────────────────────────────────────────
_LAYOUT_KEYWORDS = {
    "table":  ("table", "tableau", "grille", "grid"),
    "image":  ("image", "figure", "diagramme", "diagram", "schéma", "schema", "photo"),
    "header": ("header", "en-tête", "entête", "haut de page", "top of page", "top-right"),
    "footer": ("footer", "pied de page", "bas de page", "bottom of page"),
}

# ─── Document / scope ─────────────────────────────────────────────────────────
_DOCUMENT_PATTERNS = (
    re.compile(
        r"(?:la\s+)?(?:dernière|latest)\s+version"
        r"(?:\s+(?:du\s+)?(?:contrat|document|policy|polic[eé]))?",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:dans|in)\s+(?:le|the)\s+"
        r"(?:contrat|document|polic[eé]|policy)\s+([\w\-]+)",
        re.IGNORECASE,
    ),
)

# ─── Anchor keywords (codes, IDs, références juridiques) ─────────────────────
# CORRECTIF : ajout patterns articles juridiques (L131-1, art. 1234, art L131-1).
_ANCHOR_PATTERNS = (
    # Articles juridiques français : "L131-1", "L. 131-1", "L 131-1"
    re.compile(r"\b[lLrR]\.?\s?\d+[-]\d+\b"),
    # "Article L131-1" ou "art. 1234" ou "article 5"
    re.compile(r"\b(?:art\.?|article)\s+[lLrR]?\.?\s?\d+(?:[-./]\d+)*\b", re.IGNORECASE),
    # Codes type ISO-9001, RC-2024-001
    re.compile(r"\b[A-Z]{2,}-?\d+(?:[-./]\d+)*\b"),
    # Acronymes en majuscules (3+ chars), sans chiffres
    re.compile(r"\b[A-Z]{3,}\b"),
    # Années / identifiants longs
    re.compile(r"\b\d{4,}\b"),
)

# Stopwords majuscules à exclure des anchor_keywords (faux positifs).
# Ajout YYYY/MM/DD/JSON/PDF/etc. (qui sont des format hints, pas des codes).
_ANCHOR_STOPWORDS = frozenset({
    "THE", "AND", "FOR", "WITH", "WHAT", "WHEN", "WHERE", "WHICH", "WHO", "WHY",
    "HOW", "DOES", "ARE", "WAS", "WERE", "BUT", "NOT", "ALL", "ANY",
    "DANS", "POUR", "AVEC", "LES", "DES", "QUE", "QUI", "QUEL", "QUELLE",
    "EST", "SONT", "MAIS", "ALSO", "ABOUT",
    # Format placeholders — exclure sinon faux positif sur "format YYYY-MM-DD"
    "YYYY", "MM", "DD", "HH", "ISO", "JSON", "XML", "PDF", "CSV", "TXT", "HTML",
    "URL", "API", "EUR", "USD", "GBP", "JPY", "TVA", "TTC", "HT",
})

# ─── Format constraint (sortie attendue) ──────────────────────────────────────
_FORMAT_RULES = (
    (r"\b(?:yyyy[-/]mm[-/]dd|iso\s*8601|iso\s*date)\b", "ISO 8601 date (YYYY-MM-DD)"),
    (r"\bjson\b",                                       "valid JSON"),
    (r"\b(?:in\s+euros?|en\s+euros?|€)\b",              "numeric value in EUR"),
    (r"\b(?:in\s+dollars?|en\s+dollars?|usd|\$)\b",     "numeric value in USD"),
    (r"\bas\s+a\s+number\b",                            "numeric value"),
    (r"\b(?:in\s+one\s+sentence|en\s+une\s+phrase)\b",  "single sentence, no preamble"),
    (r"\b(?:bullet\s*list|liste\s*à\s*puces|en\s*liste)\b", "bullet list"),
    (r"\b(?:yes\s*/\s*no|oui\s*/\s*non|boolean)\b",     "boolean (yes/no)"),
    (r"\b(?:percentage|pourcentage|%)\b",               "percentage"),
)

# ─── Disambiguation (« X, not Y », « instead of Y », ... ) ────────────────────
_DISAMBIG_PATTERNS = (
    re.compile(r"\bnot\s+(?:the\s+)?([\w\sàâéèêëïîôùûüç-]{2,30}?)(?=[\.,;]|$)", re.IGNORECASE),
    re.compile(r"\bpas\s+(?:la\s+|le\s+|les\s+)?([\w\sàâéèêëïîôùûüç-]{2,30}?)(?=[\.,;]|$)", re.IGNORECASE),
    re.compile(r"\binstead\s+of\s+(?:the\s+)?([\w\sàâéèêëïîôùûüç-]{2,30}?)(?=[\.,;]|$)", re.IGNORECASE),
    re.compile(
        r"(?:don['’]t|do\s+not)\s+confuse\s+(?:it\s+)?with\s+(?:the\s+)?"
        r"([\w\sàâéèêëïîôùûüç-]{2,30}?)(?=[\.,;]|$)",
        re.IGNORECASE,
    ),
    re.compile(r"\bas\s+opposed\s+to\s+(?:the\s+)?([\w\sàâéèêëïîôùûüç-]{2,30}?)(?=[\.,;]|$)", re.IGNORECASE),
    re.compile(r"\bexcluding\s+(?:the\s+)?([\w\sàâéèêëïîôùûüç-]{2,30}?)(?=[\.,;]|$)", re.IGNORECASE),
)

# ─── Intent (3 valeurs alignées sur le chapitre 6 Kezhan) ────────────────────
# qa = défaut (information extraction). Détection explicite pour summarization
# et translation seulement ; tout le reste tombe en qa.
_INTENT_KEYWORDS = (
    ("summarization", (
        "summarize", "summarise", "résume", "résumé", "give me an overview",
        "overview of", "what does this say", "donne un résumé", "synthétise",
        "executive summary",
    )),
    ("translation", (
        "translate", "traduis", "traduire", "in french", "in english",
        "in plain english", "en anglais", "en français", "render as",
        "version anglaise", "version française",
    )),
    # défaut implicite : "qa"
)


# ─── expected_answer_shape (5 shapes principales + 3 extensions) ─────────────
# Détecté à parsing time, AVANT retrieval, à partir de la formulation seule.
# Pilote la mise en forme de la réponse côté generation.
#
# ORDRE = priorité (le 1er match gagne). Le boolean strict est en dernier
# AVANT le défaut text, sinon « What is the premium ? » matcherait `is` et
# serait classé boolean.
_SHAPE_RULES = (
    # entity — qui / what is the X (name, party, insurer)
    ("entity", (
        r"\bwho\b", r"\bqui\b", r"\bwhom\b",
        r"\bwhat is the (?:name|insurer|insured|policy holder|seller|buyer)\b",
        r"\b(?:nom de|identité|raison sociale)\b",
    )),
    # date — quand / when / date / délai
    ("date", (
        r"\bwhen\b", r"\bquand\b",
        r"\b(?:effective\s+date|date\s+(?:d['e]'?effet|de\s+début|de\s+fin|d'expiration))\b",
        r"\bcoverage start", r"\bdate\s+(?:du|de)\b",
        r"\b(?:start(?:ing)?|end(?:ing)?|expiration|expiry|deadline)\s+date\b",
        r"\b(?:valid until|valable jusqu|expire|échéance)\b",
    )),
    # amount — combien / montant / prime / cost / price
    ("amount", (
        r"\bhow much\b", r"\bcombien\b",
        r"\b(?:cost|price|prime|premium|montant|tarif|cotisation|amount|value)\b",
        r"\b(?:plafond|franchise|limite|limit|deductible|cap)\b",
    )),
    # table — compare / vs / dans un tableau
    ("table", (
        r"\bcompare(?:r|s|d)?\b",
        r"\bdans un tableau\b", r"\bin a table\b", r"\btabular\b",
        r"\b(?:vs|versus)\b",
        r"\bdiff(?:é|e)rence(?:s)?\b",
    )),
    # list — quels sont / list all / énumère / what are the
    ("list", (
        r"\blist all\b", r"\bliste\s+(?:de|des)\b",
        r"\b(?:quels?|quelles?)\s+sont\b",
        r"\bwhat are the\b",
        r"\b(?:tous|toutes)\s+les\b", r"\ball the\b",
        r"\bensemble des\b", r"\bénumère",
    )),
    # boolean — STRICT : la question doit COMMENCER par un auxiliaire yes/no,
    # sinon « What is X » serait faussement matché.
    ("boolean", (
        r"^\s*(?:does|do|did|is|are|was|were|has|have|can|could|will|would|should|may|might)\b.+\?\s*$",
        r"^\s*(?:est-ce\s+que|y\s+a-t-il|peut-on|doit-on|peuvent-ils|sont-ils)\b",
        r"\b(?:yes\s*/\s*no|oui\s*/\s*non|true\s*/\s*false|vrai\s*/\s*faux)\b",
    )),
    # défaut implicite : "text"
)


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 2. DATACLASS — Brick (compat src/question/bricks.py de Kezhan)             ║
# ╚════════════════════════════════════════════════════════════════════════════╝

BrickRunner = Callable[[str, dict], Optional[dict]]


@dataclass(frozen=True)
class Brick:
    name: str
    target: str                                       # "retrieval" | "generation"
    run: BrickRunner
    compatible_doc_types: tuple[str, ...] = ()        # vide = tous
    requires_llm: bool = False
    description: str = ""


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 3. EXTRACTORS — fonctions publiques par champ                              ║
# ╚════════════════════════════════════════════════════════════════════════════╝

def extract_hints(question: str) -> dict[str, Any]:
    """Extraire page / section / layout / document. Retourne un dict (champs absents si non trouvé)."""
    out: dict[str, Any] = {}
    if not question:
        return out

    # Page
    for pat in _PAGE_PATTERNS:
        m = pat.search(question)
        if m:
            try:
                out["page_hint"] = int(m.group(1))
                break
            except (ValueError, IndexError):
                continue

    # Section : essaie chaque pattern dans l'ordre, garde le premier hit valide
    for pat in _SECTION_PATTERNS:
        for m in pat.finditer(question):
            name = m.group(1).strip().rstrip(".,;:").lower()
            if name and name not in _SECTION_STOPWORDS:
                out["section_hint"] = name
                break
        if "section_hint" in out:
            break

    # Layout (premier match gagnant)
    q_lower = question.lower()
    for layout_type, keywords in _LAYOUT_KEYWORDS.items():
        if any(re.search(rf"\b{re.escape(kw)}\b", q_lower) for kw in keywords):
            out["layout_hint"] = layout_type
            break

    # Document / version
    for pat in _DOCUMENT_PATTERNS:
        m = pat.search(question)
        if m:
            out["document_hint"] = m.group(0).strip()
            break

    return out


def extract_anchor_keywords(question: str) -> list[str]:
    """Codes / IDs / acronymes / articles juridiques pour driver une recherche lexicale."""
    if not question:
        return []
    found: list[str] = []
    for pat in _ANCHOR_PATTERNS:
        for m in pat.findall(question):
            tok = m.strip() if isinstance(m, str) else str(m)
            if not tok:
                continue
            if tok.upper() in _ANCHOR_STOPWORDS:
                continue
            if tok not in found:
                found.append(tok)
    return found


def extract_format_constraint(question: str) -> Optional[str]:
    """Détecter le format de réponse attendu (date ISO, JSON, EUR, bullet list, …)."""
    if not question:
        return None
    q_lower = question.lower()
    for pattern, label in _FORMAT_RULES:
        if re.search(pattern, q_lower):
            return label
    return None


def extract_disambiguation(question: str) -> tuple[Optional[str], list[str]]:
    """
    Patterns « X not Y » / « pas Y » / etc. → (instruction, distractors).

    IMPORTANT (cf. chapitre Faseya) : ces signaux vont vers la GÉNÉRATION,
    JAMAIS vers le retrieval. Filtrer "deductible" au retrieval supprime la
    ligne qui contient le plafond (les deux apparaissent souvent ensemble).
    """
    if not question:
        return None, []
    distractors: list[str] = []
    for pat in _DISAMBIG_PATTERNS:
        for m in pat.finditer(question):
            tok = m.group(1).strip().rstrip(".,;:").lower()
            if tok and tok not in distractors and len(tok) <= 60:
                distractors.append(tok)
    if not distractors:
        return None, []
    instruction = (
        "L'utilisateur demande la notion principale, PAS : "
        f"{', '.join(distractors)}. Ces concepts apparaissent souvent ensemble "
        "dans les passages remontés — n'extraire que la notion principale."
    )
    return instruction, distractors


def classify_intent(question: str) -> str:
    """
    Classer l'intent dans les 3 valeurs du chapitre 6 Kezhan :
    `qa` (défaut), `summarization`, `translation`. Chaque intent route vers
    un pipeline downstream différent.
    """
    if not question:
        return "qa"
    q_lower = question.lower()
    for intent, keywords in _INTENT_KEYWORDS:
        if any(kw in q_lower for kw in keywords):
            return intent
    return "qa"


def extract_answer_shape(question: str) -> str:
    """
    Détecter la forme de réponse attendue à partir de la formulation seule.

    5 shapes principales + 3 extensions (chapitre 6 Kezhan) :
      - amount  : « combien », « how much », « prime », « cost », …
      - date    : « when », « quand », « date d'effet », …
      - list    : « list all », « quels sont les », « toutes les … »
      - table   : « compare », « vs », « tableau comparatif »
      - text    : défaut (pas de signal explicite)
      - boolean : questions oui/non explicites (« does X », « est-ce que »)
      - entity  : « who », « qui », « what is the name »

    NE DÉPEND PAS du document ni du retrieval — calculé une fois côté parsing,
    propage déterministiquement vers la génération.
    """
    if not question:
        return "text"
    q_lower = question.lower()
    for shape, patterns in _SHAPE_RULES:
        for pat in patterns:
            if re.search(pat, q_lower):
                return shape
    return "text"


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 4. WRAPPERS DE BRIQUES (adapter helpers → contrat Brick)                   ║
# ╚════════════════════════════════════════════════════════════════════════════╝

def _run_anchors(q: str, _ctx: dict) -> Optional[dict]:
    kw = extract_anchor_keywords(q)
    return {"anchor_keywords": kw} if kw else None


def _run_page_hint(q: str, _ctx: dict) -> Optional[dict]:
    h = extract_hints(q)
    return {"page_hint": h["page_hint"]} if "page_hint" in h else None


def _run_section_hint(q: str, _ctx: dict) -> Optional[dict]:
    h = extract_hints(q)
    return {"section_hint": h["section_hint"]} if "section_hint" in h else None


def _run_layout_hint(q: str, _ctx: dict) -> Optional[dict]:
    h = extract_hints(q)
    return {"layout_hint": h["layout_hint"]} if "layout_hint" in h else None


def _run_document_hint(q: str, _ctx: dict) -> Optional[dict]:
    h = extract_hints(q)
    return {"document_hint": h["document_hint"]} if "document_hint" in h else None


def _run_format(q: str, _ctx: dict) -> Optional[dict]:
    f = extract_format_constraint(q)
    return {"format_constraint": f} if f else None


def _run_disambig(q: str, _ctx: dict) -> Optional[dict]:
    instruction, distractors = extract_disambiguation(q)
    if not distractors:
        return None
    return {"disambiguation": instruction, "must_distinguish": distractors}


def _run_answer_shape(q: str, _ctx: dict) -> Optional[dict]:
    """
    Toujours actif (le défaut `text` est utile en aval pour la génération).

    Override : si l'intent est `summarization` ou `translation`, la shape par
    défaut est `text` (un résumé n'est pas une liste, une traduction non plus).
    """
    intent = classify_intent(q)
    if intent in ("summarization", "translation"):
        return {"expected_answer_shape": "text"}
    return {"expected_answer_shape": extract_answer_shape(q)}


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 5. REGISTRE BRICKS                                                         ║
# ╚════════════════════════════════════════════════════════════════════════════╝

BRICKS: dict[str, Brick] = {
    "anchor_keywords": Brick("anchor_keywords", "retrieval",  _run_anchors),
    "page_hint":       Brick("page_hint",       "retrieval",  _run_page_hint,
                             compatible_doc_types=("pdf", "pptx")),
    "section_hint":    Brick("section_hint",    "retrieval",  _run_section_hint,
                             compatible_doc_types=("pdf", "word", "pptx")),
    "layout_hint":     Brick("layout_hint",     "retrieval",  _run_layout_hint),
    "document_hint":   Brick("document_hint",   "retrieval",  _run_document_hint),
    "format":          Brick("format",          "generation", _run_format),
    "disambiguation":  Brick("disambiguation",  "generation", _run_disambig),
    "answer_shape":    Brick("answer_shape",    "generation", _run_answer_shape),
}


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 6. PRESETS par doc_type                                                    ║
# ╚════════════════════════════════════════════════════════════════════════════╝

PRESETS: dict[str, list[str]] = {
    "pdf": [
        "anchor_keywords",
        "page_hint",
        "section_hint",
        "layout_hint",
        "document_hint",
        "format",
        "disambiguation",
        "answer_shape",
    ],
    "word": [
        "anchor_keywords",
        "section_hint",
        "layout_hint",
        "document_hint",
        "format",
        "disambiguation",
        "answer_shape",
    ],
    "excel": [
        "anchor_keywords",
        "document_hint",
        "format",
        "disambiguation",
        "answer_shape",
    ],
    "email": [
        "anchor_keywords",
        "document_hint",
        "format",
        "disambiguation",
        "answer_shape",
    ],
    "pptx": [
        "anchor_keywords",
        "page_hint",
        "section_hint",
        "layout_hint",
        "document_hint",
        "format",
        "disambiguation",
        "answer_shape",
    ],
}

DEFAULT_DOC_TYPE = "pdf"


def preset_for(doc_type: str) -> list[str]:
    """Liste des briques actives par défaut pour `doc_type` (fallback : PDF)."""
    return list(PRESETS.get(doc_type, PRESETS[DEFAULT_DOC_TYPE]))


def resolve_active(doc_type: str, enable: Optional[dict[str, bool]]) -> list[str]:
    """Combine preset + override `enable={...}`."""
    active = preset_for(doc_type)
    if not enable:
        return active
    for name, on in enable.items():
        if on and name not in active:
            active.append(name)
        elif not on and name in active:
            active.remove(name)
    return active


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 7. POINT D'ENTRÉE — parse_question                                         ║
# ╚════════════════════════════════════════════════════════════════════════════╝

def parse_question(
    question: str,
    *,
    document_type: str = "pdf",
    enable: Optional[dict[str, bool]] = None,
    domain_hint: str = "",
) -> list[dict[str, Any]]:
    """
    Brique 2 : transformer une question utilisateur en plan d'exécution structuré.

    Sortie : toujours une **liste** de dicts. 1 question simple = 1 entrée.
    Chaque entrée a la forme :
        { "retrieval": {...}, "generation": {...}, "_meta": {...} }
    Le JSON ne contient QUE les champs réellement populés (pas de `null`).
    """
    if question is None:
        question = ""
    question = question.strip()

    intent = classify_intent(question)
    active = resolve_active(document_type, enable)
    ctx: dict[str, Any] = {"domain_hint": domain_hint, "document_type": document_type}

    return [_run_extraction(question, document_type, active, ctx, intent)]


def _run_extraction(
    q: str,
    doc_type: str,
    active_bricks: list[str],
    ctx: dict[str, Any],
    intent: str,
) -> dict[str, Any]:
    """Tourne les briques actives et assemble le JSON pour UNE sous-question."""
    output: dict[str, Any] = {
        "retrieval":  {"main_query": q},
        "generation": {"original_question": q},
        "_meta": {
            "intent":         intent,
            "document_type":  doc_type,
            "bricks_active":  [],
        },
    }
    for name in active_bricks:
        brick = BRICKS.get(name)
        if brick is None:
            continue
        if brick.compatible_doc_types and doc_type not in brick.compatible_doc_types:
            continue
        result = brick.run(q, ctx)
        if not result:
            continue
        output[brick.target].update(result)
        output["_meta"]["bricks_active"].append(name)
    return output


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 8. CLI minimal                                                             ║
# ╚════════════════════════════════════════════════════════════════════════════╝

if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print('Usage: python question_parsing.py "<question>" [doc_type]', file=sys.stderr)
        sys.exit(1)

    q = sys.argv[1]
    doc_type = sys.argv[2] if len(sys.argv) >= 3 else "pdf"
    plan = parse_question(q, document_type=doc_type)
    print(json.dumps(plan, indent=2, ensure_ascii=False))

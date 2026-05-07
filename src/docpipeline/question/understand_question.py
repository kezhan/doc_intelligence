"""
understand_question.py — Préparer une question utilisateur AVANT la recherche.

Référence : chapitre « Understanding the Question Before Searching » du
Google Doc Faseya (4ème onglet) partagé par Kezhan.

Idée centrale : une question utilisateur n'est pas un seul input — c'est la
matière première pour DEUX préparations distinctes :

  1. RetrievalQuery  : ce qui sert à CHERCHER dans les documents
                       (query nettoyée, rewrites, anchor keywords, hints)
  2. GenerationBrief : ce qui sert à FORMULER la réponse
                       (question originale, format, désambiguïsation)

Ce module commence par UNE seule fonction de la première préparation :
`extract_hints(question)` → `StructuralHints`. Elle extrait les indices
structurels que l'utilisateur a glissés dans sa question (page, section,
layout) pour les utiliser comme filtres avant la recherche.

Approche :
  - Regex déterministe pour les patterns évidents (page X, section Y, table)
  - Pas de classe, fonctions pures + dataclass
  - LLM en option pour les cas flous (à activer plus tard)

Liens avec parse_pdf.py : les hints produits ici (`page_hint`, `layout_hint`)
matchent directement les flags du `page_df` (`page_num`, `has_vector_table`,
`has_full_page_image`). C'est l'infrastructure de routage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ Dataclass — sortie publique                                                ║
# ╚════════════════════════════════════════════════════════════════════════════╝

@dataclass
class StructuralHints:
    """Indices structurels extraits d'une question utilisateur."""
    section_hint:   Optional[str]  = None     # "exclusions", "limits", ...
    page_hint:      Optional[int]  = None     # 1, 2, 47, ...
    layout_hint:    Optional[str]  = None     # "table" | "image" | "header" | "footer"
    document_hint:  Optional[str]  = None     # "latest version", "Allianz contract", ...
    raw_signals:    list[str]      = field(default_factory=list)  # traçabilité


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ Patterns regex                                                             ║
# ╚════════════════════════════════════════════════════════════════════════════╝

# Page : "page 1", "page n°1", "p. 1", "à la page 12", "on page 47"
_PAGE_PATTERNS = (
    re.compile(r"\bpage\s*n?[°o]?\s*(\d+)",                 re.IGNORECASE),
    re.compile(r"\bp\.?\s*(\d+)\b",                         re.IGNORECASE),
    re.compile(r"\bon\s+page\s+(\d+)",                      re.IGNORECASE),
    re.compile(r"\bà\s+la\s+page\s+(\d+)",                  re.IGNORECASE),
)

# Section : "section X", "dans la section X", "in the section X",
#           "section called 'X'", "section nommée X"
_SECTION_PATTERNS = (
    re.compile(r"section\s+(?:called|nommée|appelée|nommé|appelé|named)\s+['\"]?([\w\sàâéèêëïîôùûüç-]+?)['\"]?(?=[\.,;]|$)",
               re.IGNORECASE),
    re.compile(r"(?:dans\s+la|in\s+the)\s+section\s+['\"]?([\w\sàâéèêëïîôùûüç-]+?)['\"]?(?=[\.,;]|$)",
               re.IGNORECASE),
    re.compile(r"\bsection\s+['\"]([\w\s\-àâéèêëïîôùûüç]+?)['\"]",
               re.IGNORECASE),
)

# Layout : table, tableau, figure, image, schéma, header, footer, en-tête, pied
_LAYOUT_KEYWORDS = {
    "table":  ("table", "tableau", "grille"),
    "image":  ("image", "figure", "diagramme", "diagram", "schéma", "schema", "photo"),
    "header": ("header", "en-tête", "entête", "haut de page"),
    "footer": ("footer", "pied de page", "bas de page"),
}

# Document version / scope
_DOCUMENT_PATTERNS = (
    re.compile(r"(?:la\s+)?(?:dernière|latest)\s+version\s+(?:du\s+)?(?:contrat|document|policy|polic[eé])?",
               re.IGNORECASE),
    re.compile(r"(?:dans|in)\s+(?:le|the)\s+(?:contrat|document|polic[eé]|policy)\s+([\w\-]+)",
               re.IGNORECASE),
)


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ Helpers                                                                    ║
# ╚════════════════════════════════════════════════════════════════════════════╝

def _extract_page(question: str) -> tuple[Optional[int], Optional[str]]:
    """Retourne (page_num, signal) si une référence à une page est trouvée."""
    for pat in _PAGE_PATTERNS:
        m = pat.search(question)
        if m:
            try:
                return int(m.group(1)), f"regex_page:{m.group(0)!r}"
            except (ValueError, IndexError):
                continue
    return None, None


def _extract_section(question: str) -> tuple[Optional[str], Optional[str]]:
    """Retourne (nom_section, signal) si une section est mentionnée."""
    for pat in _SECTION_PATTERNS:
        m = pat.search(question)
        if m:
            name = m.group(1).strip().rstrip(".,;:")
            if name:
                return name, f"regex_section:{m.group(0)!r}"
    return None, None


def _extract_layout(question: str) -> tuple[Optional[str], Optional[str]]:
    """Retourne (type_layout, signal) si un indice de mise en page est trouvé."""
    q_lower = question.lower()
    for layout_type, keywords in _LAYOUT_KEYWORDS.items():
        for kw in keywords:
            if re.search(rf"\b{re.escape(kw)}\b", q_lower):
                return layout_type, f"regex_layout:{kw}→{layout_type}"
    return None, None


def _extract_document(question: str) -> tuple[Optional[str], Optional[str]]:
    """Retourne (référence_document, signal) si un scope document est mentionné."""
    for pat in _DOCUMENT_PATTERNS:
        m = pat.search(question)
        if m:
            matched = m.group(0).strip()
            return matched, f"regex_document:{matched!r}"
    return None, None


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ Fonction publique                                                          ║
# ╚════════════════════════════════════════════════════════════════════════════╝

def extract_hints(question: str) -> StructuralHints:
    """
    Extraire les indices structurels d'une question utilisateur.

    Patterns couverts (regex déterministe, sans LLM) :
      - page_hint    : "page 1", "p. 12", "à la page 47", "on page X"
      - section_hint : "dans la section X", "section called X", "in the section X"
      - layout_hint  : "table" / "tableau" → table ; "image" / "figure" → image ;
                        "header" / "en-tête" → header ; "footer" / "pied" → footer
      - document_hint: "latest version", "dernière version", "dans le contrat X"

    Pour les cas flous (références implicites, paraphrases libres), un appel
    LLM optionnel sera ajouté plus tard.
    """
    if not question:
        return StructuralHints()

    page,    sig_page    = _extract_page(question)
    section, sig_section = _extract_section(question)
    layout,  sig_layout  = _extract_layout(question)
    doc,     sig_doc     = _extract_document(question)

    raw_signals = [s for s in (sig_page, sig_section, sig_layout, sig_doc) if s]

    return StructuralHints(
        page_hint     = page,
        section_hint  = section,
        layout_hint   = layout,
        document_hint = doc,
        raw_signals   = raw_signals,
    )


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ CLI minimal                                                                ║
# ╚════════════════════════════════════════════════════════════════════════════╝

if __name__ == "__main__":
    import json
    import sys
    from dataclasses import asdict

    if len(sys.argv) != 2:
        print('Usage: python understand_question.py "<question>"', file=sys.stderr)
        sys.exit(1)

    hints = extract_hints(sys.argv[1])
    print(json.dumps(asdict(hints), indent=2, ensure_ascii=False))

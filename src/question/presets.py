"""Presets par type de document — connaissance métier centralisée.

Chaque preset est la liste des briques actives par défaut pour un type de
document donné. C'est ici que se code « en Word, parler de page n'a pas de
sens », « en Excel, on parle de feuilles et de colonnes », etc.

L'utilisateur peut surcharger via le paramètre `enable={}` de
`understand_question`.
"""

from __future__ import annotations

PRESETS: dict[str, list[str]] = {
    # PDF : tous les axes structurels existent.
    "pdf": [
        "rewrite",
        "anchor_keywords",
        "page_hint",
        "section_hint",
        "layout_hint",
        "format",
        "disambiguation",
    ],
    # Word : pas de pagination stable (page_hint désactivé).
    "word": [
        "rewrite",
        "anchor_keywords",
        "section_hint",
        "layout_hint",
        "format",
        "disambiguation",
    ],
    # Excel : pas de section ni de page ; à terme, ajouter sheet_hint / column_hint.
    "excel": [
        "rewrite",
        "anchor_keywords",
        "format",
        "disambiguation",
    ],
    # Email : pas de section ni de page ; à terme, ajouter from_hint / subject_hint.
    "email": [
        "rewrite",
        "anchor_keywords",
        "format",
        "disambiguation",
    ],
    # PowerPoint : slides = pages, sections = groupes.
    "pptx": [
        "rewrite",
        "anchor_keywords",
        "page_hint",          # slide_number
        "section_hint",
        "layout_hint",
        "format",
        "disambiguation",
    ],
}

# Type de document utilisé quand l'appelant n'en passe pas / passe un inconnu.
DEFAULT_DOC_TYPE = "pdf"


def preset_for(doc_type: str) -> list[str]:
    """Liste de briques actives par défaut pour `doc_type` (fallback : PDF)."""
    return list(PRESETS.get(doc_type, PRESETS[DEFAULT_DOC_TYPE]))


def resolve_active(doc_type: str, enable: dict[str, bool] | None) -> list[str]:
    """Combine preset + override `enable={...}`.

    - `enable=None` → preset complet.
    - `enable={"X": False}` → preset moins X.
    - `enable={"Y": True}` → preset plus Y.
    """
    active = preset_for(doc_type)
    if not enable:
        return active

    for name, on in enable.items():
        if on and name not in active:
            active.append(name)
        elif not on and name in active:
            active.remove(name)
    return active

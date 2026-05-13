"""
scope_js.py — Filtrage scope pour traduction (Step 4 build order Tome 2).

Cf. CLAUDE_tome2_translation.md §1.3 + Step 4. La couche "retrieval" du
pipeline de traduction : a partir d'un line_df + span_df bruts (sortie de
parsing) et d'un TranslationScope declaratif, on decoupe en deux paires :

    selected_line_df, selected_span_df   -> consommes par translate_chunks
    skipped_line_df,  skipped_span_df    -> rendering les laisse intacts
                                              (texte source reinjecte tel quel)

Pure logique, zero LLM (regle CLAUDE.md : LLM reserve a translation/
summarization/excel_agent ; le scope est de la selection de lignes).

Schema minimal `TranslationScope` (Pydantic) defini ici. Step 3 (request.py)
l'importera quand il sera ecrit, ou bougera la classe ailleurs au choix.
"""

from __future__ import annotations

import unicodedata
import warnings

import pandas as pd
from pydantic import BaseModel, field_validator


class TranslationScope(BaseModel):
    """Perimetre que la traduction doit couvrir.

    None partout = traduire tout le document.

    Attributs :
        page_range       : (start, end) inclusif, 1-based. PDF only.
                           Filtre sur la colonne `page_num` du line_df.
        include_sections : si fourni, seules ces sections sont traduites
                           (matching case+accent-insensitive substring sur
                           la colonne `section_breadcrumb` du line_df).
        exclude_sections : retire ces sections (applique APRES include).
    """

    page_range: tuple[int, int] | None = None
    include_sections: list[str] | None = None
    exclude_sections: list[str] | None = None

    @field_validator("page_range")
    @classmethod
    def _check_page_range(cls, v):
        if v is None:
            return v
        start, end = v
        if start < 1 or end < start:
            raise ValueError(
                f"page_range invalide : {v} "
                "(attendu start>=1 et end>=start, 1-based inclusif)"
            )
        return v


def _normalize(s: str) -> str:
    """case+accent-insensitive normalization pour matching de sections."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.casefold().strip()


def _section_matches(line_section: str, patterns: list[str]) -> bool:
    """True si line_section contient (substring, normalize) au moins un pattern."""
    if not line_section:
        return False
    haystack = _normalize(line_section)
    return any(_normalize(p) in haystack for p in patterns)


def _detect_fk_columns(
    line_df: pd.DataFrame, span_df: pd.DataFrame
) -> tuple[str, ...] | None:
    """Detecte les colonnes communes entre line_df et span_df pour propager
    le filtre. Convention par format :
      - Word : 'paragraph_index'
      - PDF  : ('page_num', 'line_num')
      - PPTX : ('slide_index', 'shape_index', 'paragraph_index')
    Retourne None si aucune correspondance n'est detectable.
    """
    if line_df.empty or span_df.empty:
        return None
    common = set(line_df.columns) & set(span_df.columns)
    if "paragraph_index" in common:
        return ("paragraph_index",)
    if {"page_num", "line_num"} <= common:
        return ("page_num", "line_num")
    if {"slide_index", "shape_index", "paragraph_index"} <= common:
        return ("slide_index", "shape_index", "paragraph_index")
    return None


def apply_translation_scope(
    line_df: pd.DataFrame,
    span_df: pd.DataFrame,
    scope: TranslationScope | None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Decoupe (line_df, span_df) en (selected, skipped) selon `scope`.

    Args:
        line_df : DataFrame des lignes/paragraphes (granularite RAG).
                  Peut etre paragraph_df (Word) ou line_df (PDF).
        span_df : DataFrame des spans/runs (granularite translation).
        scope   : TranslationScope ou None (= tout selected).

    Returns:
        (selected_line_df, selected_span_df, skipped_line_df, skipped_span_df)

    Filtres :
      - page_range        : requiert colonne 'page_num' dans line_df.
      - include_sections  : requiert colonne 'section_breadcrumb'.
      - exclude_sections  : requiert colonne 'section_breadcrumb'.

    Si une colonne manque, un warning est emis et le filtre correspondant
    est ignore (le reste continue).

    Le span_df est ensuite filtre par jointure FK auto-detectee (cf.
    `_detect_fk_columns`). Si aucune FK detectable, span_df entier classe
    selected (avec warning).
    """
    empty_line = line_df.iloc[0:0].copy()
    empty_span = span_df.iloc[0:0].copy()

    if scope is None:
        return line_df.copy(), span_df.copy(), empty_line, empty_span

    if line_df.empty:
        return line_df.copy(), span_df.copy(), empty_line, empty_span

    selected_mask = pd.Series(True, index=line_df.index)

    if scope.page_range is not None:
        if "page_num" not in line_df.columns:
            warnings.warn(
                "page_range demande mais line_df n'a pas de colonne "
                "'page_num' -- filtre ignore.",
                stacklevel=2,
            )
        else:
            start, end = scope.page_range  # spec Tome 2 : 1-based, inclusif
            # PDF parser (parse_pdf.py) emet page_num 0-based (convention
            # fitz). On normalise en 1-based pour matching avec le scope
            # utilisateur. Si line_df.page_num est deja 1-based (autre
            # format), on detecte via le min et on n'ajoute rien.
            min_page = line_df["page_num"].min()
            offset = 1 - int(min_page) if min_page == 0 else 0
            page_1based = line_df["page_num"] + offset
            selected_mask &= page_1based.between(start, end, inclusive="both")

    if scope.include_sections:
        if "section_breadcrumb" not in line_df.columns:
            warnings.warn(
                "include_sections demande mais line_df n'a pas de colonne "
                "'section_breadcrumb' -- filtre ignore.",
                stacklevel=2,
            )
        else:
            include_match = line_df["section_breadcrumb"].astype(str).map(
                lambda s: _section_matches(s, scope.include_sections or [])
            )
            selected_mask &= include_match

    if scope.exclude_sections:
        if "section_breadcrumb" not in line_df.columns:
            warnings.warn(
                "exclude_sections demande mais line_df n'a pas de colonne "
                "'section_breadcrumb' -- filtre ignore.",
                stacklevel=2,
            )
        else:
            exclude_match = line_df["section_breadcrumb"].astype(str).map(
                lambda s: _section_matches(s, scope.exclude_sections or [])
            )
            selected_mask &= ~exclude_match

    selected_line_df = line_df[selected_mask].copy()
    skipped_line_df  = line_df[~selected_mask].copy()

    if span_df.empty:
        return selected_line_df, span_df.copy(), skipped_line_df, empty_span

    fk = _detect_fk_columns(line_df, span_df)
    if fk is None:
        warnings.warn(
            "Pas de FK detectable entre line_df et span_df "
            "(colonnes communes attendues : 'paragraph_index', "
            "('page_num','line_num'), ou ('slide_index','shape_index',"
            "'paragraph_index')) -- span_df entier classe selected.",
            stacklevel=2,
        )
        return selected_line_df, span_df.copy(), skipped_line_df, empty_span

    selected_keys = selected_line_df[list(fk)].drop_duplicates()
    merged = span_df.merge(selected_keys, on=list(fk), how="left", indicator=True)
    in_selected = (merged["_merge"] == "both").to_numpy()
    selected_span_df = span_df[in_selected].copy()
    skipped_span_df  = span_df[~in_selected].copy()

    return selected_line_df, selected_span_df, skipped_line_df, skipped_span_df


if __name__ == "__main__":
    import json

    line_df = pd.DataFrame({
        "page_num": [1, 1, 2, 2, 3],
        "line_num": [0, 1, 0, 1, 0],
        "section_breadcrumb": ["Body", "Body", "Annexes", "Annexes", "Conclusion"],
        "text": ["intro", "details", "annex1", "annex2", "ccl"],
    })
    span_df = pd.DataFrame({
        "page_num": [1, 1, 1, 2, 2, 3],
        "line_num": [0, 0, 1, 0, 1, 0],
        "span_id": ["s1", "s2", "s3", "s4", "s5", "s6"],
        "text": ["i", "n", "d", "a1", "a2", "c"],
    })

    cases = {
        "scope=None": None,
        "page_range=(1,2)": TranslationScope(page_range=(1, 2)),
        "exclude=['annexes']": TranslationScope(exclude_sections=["annexes"]),
        "include=['conclusion']": TranslationScope(include_sections=["conclusion"]),
    }
    for label, sc in cases.items():
        sl, ss, kl, ks = apply_translation_scope(line_df, span_df, sc)
        print(f"{label:30s} -> selected lines={len(sl)} spans={len(ss)} | "
              f"skipped lines={len(kl)} spans={len(ks)}")

"""
TODO-TOC-003 — Extraction de TOC par analyse du contenu textuel.

Trois méthodes complémentaires, ZERO LLM :
  1. Lignes pointillées  : "Chapitre 1 ............... 5"
  2. Multiline           : tirets/points/underline avec numéro sur la ligne suivante
  3. Titraille           : candidats titres par taille de police et gras (nécessite line_df)
"""

from __future__ import annotations

import re
from pathlib import Path

import fitz  # PyMuPDF
import pandas as pd

from ._utils import add_toc_metadata, compute_page_offset, normalize_toc_schema
from .models import empty_toc_df, validate_toc_df


# ── 1. Lignes pointillées ─────────────────────────────────────────────────────

_DOTTED_PATTERN = re.compile(r"^(.*?)\.{4,}\s*(\d+)\s*$")


def extract_toc_dotted(pdf_path: str | Path) -> pd.DataFrame:
    """
    TODO-TOC-003a — Extraire les entrées TOC via les lignes à points leaders.

    Typique : "Introduction ............. 3"

    Input  : chemin PDF
    Output : DataFrame normalisé (source='dotted')
             — vide si aucune ligne à points leaders n'est trouvée
    """
    toc_entries: list[dict] = []
    page_texts: list[str] = []

    with fitz.open(str(pdf_path)) as doc:
        for page_index, page in enumerate(doc, start=1):
            page_text = page.get_text("text").replace("\xa0", " ")
            page_texts.append(page_text)
            for line in page_text.splitlines():
                match = _DOTTED_PATTERN.match(line.strip())
                if match:
                    title = match.group(1).strip()
                    page_num_displayed = int(match.group(2))
                    if title:
                        toc_entries.append({
                            "text": title,
                            "page_num_displayed": page_num_displayed,
                            "source_page": page_index,
                        })

    toc_df = pd.DataFrame(
        toc_entries,
        columns=["text", "page_num_displayed", "source_page"],
    )
    if toc_df.empty:
        return empty_toc_df()
    toc_df = compute_page_offset(toc_df, page_texts)
    toc_df = add_toc_metadata(toc_df)
    normalized_df = normalize_toc_schema(toc_df, source="dotted", validated_default=False)
    validate_toc_df(normalized_df)
    return normalized_df


# ── 2. Extraction multiline ───────────────────────────────────────────────────

_LEADER_PATTERN = re.compile(r"^(.*?)\s*(?:[.\-_ ]{3,})\s*(\d+)?\s*$")


def extract_toc_multiline(pdf_path: str | Path) -> pd.DataFrame:
    """
    TODO-TOC-003b — Extraire les entrées TOC avec leaders sur plusieurs lignes.

    Gère le cas où le numéro de page se trouve sur la ligne suivante, et les
    variantes tirets, underline, espaces répétés.

    Input  : chemin PDF
    Output : DataFrame normalisé (source='multiline')
    """
    toc_entries: list[dict] = []
    page_texts: list[str] = []

    with fitz.open(str(pdf_path)) as doc:
        for page_index, page in enumerate(doc, start=1):
            text = page.get_text("text").replace("\xa0", " ")
            page_texts.append(text)
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

            buffer_line: str | None = None

            for line in lines:
                if buffer_line is not None:
                    combined = buffer_line + " " + line
                    match = _LEADER_PATTERN.match(combined)
                    if match and match.group(2):
                        toc_entries.append({
                            "text": match.group(1).strip(),
                            "page_num_displayed": int(match.group(2)),
                            "source_page": page_index,
                        })
                        buffer_line = None
                        continue
                    buffer_line = combined
                    continue

                match = _LEADER_PATTERN.match(line)
                if match:
                    title = match.group(1).strip()
                    page_num_str = match.group(2)
                    if page_num_str:
                        if title:
                            toc_entries.append({
                                "text": title,
                                "page_num_displayed": int(page_num_str),
                                "source_page": page_index,
                            })
                    else:
                        buffer_line = line
                elif buffer_line is not None and line.isdigit():
                    toc_entries.append({
                        "text": buffer_line.rsplit(maxsplit=1)[0],
                        "page_num_displayed": int(line),
                        "source_page": page_index,
                    })
                    buffer_line = None

    toc_df = pd.DataFrame(
        toc_entries,
        columns=["text", "page_num_displayed", "source_page"],
    )
    if toc_df.empty:
        return empty_toc_df()
    toc_df = compute_page_offset(toc_df, page_texts)
    toc_df = add_toc_metadata(toc_df)
    normalized_df = normalize_toc_schema(toc_df, source="multiline", validated_default=False)
    validate_toc_df(normalized_df)
    return normalized_df


# ── 3. Titraille par style ────────────────────────────────────────────────────

def extract_title_candidates(
    text_df: pd.DataFrame,
    size_threshold: float = 2.5,
    max_char_length: int = 80,
    require_bold: bool = True,
) -> pd.DataFrame:
    """
    TODO-TOC-003c — Identifier les candidats titres par taille de police et gras.

    Prend en entrée le `line_df` produit par `parse_pdf` (colonnes attendues :
    page_num, line_num, text, size, is_bold, character_count, x0, x1).

    Les titres sont détectés si leur taille dépasse la taille du corps du texte
    de `size_threshold` points, et leur longueur est inférieure à `max_char_length`.

    Input  : DataFrame line_df issu de parse_pdf, paramètres de seuil
    Output : DataFrame candidats titres triés par page puis écart de taille (desc)
    """
    body_text_size: float = text_df["size"].mode().iloc[0]

    grouped = text_df.groupby(["page_num", "line_num"]).agg(
        text=("text", "".join),
        size=("size", "mean"),
        is_bold=("is_bold", "any"),
        character_count=("character_count", "sum"),
        x0=("x0", "min"),
        x1=("x1", "max"),
    ).reset_index()

    def _is_title(row: pd.Series) -> bool:
        size_ok = row["size"] >= body_text_size + size_threshold
        length_ok = row["character_count"] < max_char_length
        bold_ok = (not require_bold) or row["is_bold"]
        return bool(size_ok and length_ok and bold_ok)

    grouped["is_title"] = grouped.apply(_is_title, axis=1)
    title_candidates_df = grouped[grouped["is_title"]].copy()
    title_candidates_df["size_diff"] = title_candidates_df["size"] - body_text_size

    return title_candidates_df.sort_values(
        ["page_num", "size_diff"], ascending=[True, False]
    )


def group_numbered_titles(toc_df: pd.DataFrame) -> pd.DataFrame:
    """
    Fusionner les titres dont le numéro de section est isolé sur la ligne précédente.

    Exemple courant dans les PDFs : une ligne ``"1."`` suivie de ``"Introduction"``
    sur la même page.  La fonction retourne alors ``"1. Introduction"``.
    """
    if toc_df.empty:
        return toc_df.copy()

    merged_rows: list[pd.Series] = []
    skip_next = False
    rows = toc_df.reset_index(drop=True)

    for index, row in rows.iterrows():
        if skip_next:
            skip_next = False
            continue

        text = str(row["text"]).strip()
        is_section_number = text.replace(".", "").isdigit()
        has_next_row = index + 1 < len(rows)

        if is_section_number and has_next_row:
            next_row = rows.iloc[index + 1]
            if next_row["page_num"] == row["page_num"]:
                merged = row.copy()
                merged["text"] = f"{text} {next_row['text']}"
                merged_rows.append(merged)
                skip_next = True
                continue

        merged_rows.append(row)

    return pd.DataFrame(merged_rows).reset_index(drop=True)

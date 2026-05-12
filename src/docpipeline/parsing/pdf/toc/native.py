"""
TODO-TOC-002 — Extraction des signets natifs (bookmarks) d'un PDF.

Les PDFs générés depuis Word ou une suite bureautique embarquent souvent une
table des matières binaire via la métadonnée get_toc() de PyMuPDF. Ce module
l'extrait sous forme de DataFrame et propose des utilitaires d'export.

ZERO LLM — extraction structurelle pure, aucun modèle externe.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import fitz  # PyMuPDF
import pandas as pd


# ── Détection ─────────────────────────────────────────────────────────────────

def has_native_toc(pdf_path: str | Path) -> bool:
    """
    Vérifier si un PDF contient un TOC natif (signets/bookmarks PyMuPDF).

    Input  : chemin PDF
    Output : True si des signets sont présents, False sinon
    """
    try:
        with fitz.open(str(pdf_path)) as doc:
            return len(doc.get_toc()) > 0
    except Exception:
        return False


def get_pdf_page_count(pdf_path: str | Path) -> int:
    """
    Retourner le nombre de pages d'un PDF.

    Input  : chemin PDF
    Output : nombre de pages (int)
    """
    with fitz.open(str(pdf_path)) as doc:
        return doc.page_count


def filter_pdfs_with_native_toc(
    pdf_paths: list[str | Path],
) -> tuple[list[str | Path], list[str | Path]]:
    """
    Partitionner une liste de PDFs selon la présence d'un TOC natif.

    Input  : liste de chemins PDF
    Output : (pdfs_avec_toc, pdfs_sans_toc)
    """
    with_toc = [p for p in pdf_paths if has_native_toc(p)]
    without_toc = [p for p in pdf_paths if not has_native_toc(p)]
    return with_toc, without_toc


# ── Extraction ────────────────────────────────────────────────────────────────

def extract_native_toc(pdf_path: str | Path) -> pd.DataFrame:
    """
    Extraire le TOC natif d'un PDF sous forme de DataFrame.

    Input  : chemin PDF
    Output : DataFrame colonnes [level, title, page, indicator]
             — vide (0 lignes) si aucun signet n'est présent
    """
    with fitz.open(str(pdf_path)) as doc:
        toc_raw = doc.get_toc()

    if not toc_raw:
        return pd.DataFrame(columns=["level", "title", "page", "indicator"])

    toc_df = pd.DataFrame(toc_raw, columns=["level", "title", "page"])
    return _add_indicator_column(toc_df)


# ── Transformation ────────────────────────────────────────────────────────────

def nest_toc(flat_toc: list[dict]) -> list[dict]:
    """
    Convertir un TOC plat en structure hiérarchique avec children.

    Input  : liste de dicts {level, title, page, indicator}
    Output : structure arborescente — chaque dict contient une clé 'children'
    """
    if not flat_toc:
        return []

    result: list[dict] = []
    stack: list[dict] = []

    for item in flat_toc:
        entry: dict = {
            "level": item["level"],
            "title": item["title"],
            "page": item["page"],
            "indicator": item.get("indicator", f"L{item['level']}"),
            "children": [],
        }

        while stack and stack[-1]["level"] >= entry["level"]:
            stack.pop()

        if stack:
            stack[-1]["children"].append(entry)
        else:
            result.append(entry)

        stack.append(entry)

    return result


# ── Export ────────────────────────────────────────────────────────────────────

def export_toc_to_json(
    toc_df: pd.DataFrame,
    output_path: str | Path,
    nested: bool = False,
) -> None:
    """
    Exporter un DataFrame TOC en JSON (plat ou hiérarchique).

    Input  : DataFrame TOC, chemin de sortie, flag nested (True = arbre)
    Output : fichier JSON écrit sur disque (side-effect)
    """
    records = toc_df[["level", "title", "page", "indicator"]].to_dict("records")

    for record in records:
        record["level"] = int(record["level"]) if pd.notna(record["level"]) else 1
        record["page"] = int(record["page"]) if pd.notna(record["page"]) else -1

    data: list[dict] = nest_toc(records) if nested else records

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def export_toc_to_excel(toc_df: pd.DataFrame, output_path: str | Path) -> None:
    """
    Exporter un DataFrame TOC en Excel (.xlsx).

    Input  : DataFrame TOC, chemin de sortie
    Output : fichier Excel écrit sur disque (side-effect)
    """
    _clean_df_for_excel(toc_df).to_excel(output_path, index=False, engine="openpyxl")


# ── Helpers privés ────────────────────────────────────────────────────────────

def _add_indicator_column(toc_df: pd.DataFrame) -> pd.DataFrame:
    """Ajouter une colonne 'indicator' hiérarchique (L1, L1.1, L1.2, …)."""
    df = toc_df.copy()
    counters: dict[int, int] = {}
    indicators: list[str] = []

    for _, row in df.iterrows():
        level = int(row["level"])

        for lvl in list(counters.keys()):
            if lvl > level:
                del counters[lvl]

        counters[level] = counters.get(level, 0) + 1
        indicators.append(
            "L" + ".".join(str(counters[lvl]) for lvl in sorted(counters) if lvl <= level)
        )

    df["indicator"] = indicators
    return df


_ILLEGAL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean_df_for_excel(toc_df: pd.DataFrame) -> pd.DataFrame:
    """Supprimer les caractères illégaux pour l'export Excel."""
    df = toc_df.copy()
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].apply(
            lambda x: _ILLEGAL_CHARS_RE.sub("", str(x)) if pd.notna(x) else x
        )
    return df

"""
parse_pptx.py — Parsing complet d'un .pptx avec extraction des styles par run.

Symétrique de `parse_word.py` côté PowerPoint. Une seule ouverture python-pptx,
sortie unifiée en DataFrames + doc_summary.

Pattern transversal du projet (cf. CLAUDE_tome2_translation.md) :

    extract  : parse_pptx(pptx)             → runs avec styles + span_id stable
    modify   : on change SEULEMENT le text de chaque run (translate, redact, …)
    rebuild  : (à venir) — open source as template, walk shapes/paragraphs/runs,
               replace .text, save

Le `span_id` (format `pp_<slide>_<shape>_<para>_<run>`) est la clé stable qui
fait le pont entre extract et rebuild.

Sortie de `parse_pptx(pptx)` :
    {
        "slide_df":      DataFrame,   # 1 ligne = 1 slide (layout, n_shapes, n_runs, ...)
        "shape_df":      DataFrame,   # 1 ligne = 1 shape (type, position, dimensions, ...)
        "paragraph_df":  DataFrame,   # 1 ligne = 1 paragraphe de texte
        "runs_df":       DataFrame,   # 1 ligne = 1 run (span_id, text, font, bold, italic, color, ...)
        "image_df":      DataFrame,   # 1 ligne = 1 image embarquée
        "table_df":      DataFrame,   # 1 ligne = 1 table (n_rows, n_cols)
        "doc_summary":   dict,        # JSON synthèse : metadata, source_tool, comptes, ...
    }

Aucun LLM (règle CLAUDE.md : LLM réservé à translation / summarization /
Excel SQL agent ; le parsing est intégralement heuristique).
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 1. CONSTANTES                                                              ║
# ╚════════════════════════════════════════════════════════════════════════════╝

_ALIGNMENT_NAMES = {
    1: "left", 2: "center", 3: "right", 4: "justify", 5: "distribute",
    6: "thai_distribute", 7: "justify_low",
}


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 2. HELPERS                                                                 ║
# ╚════════════════════════════════════════════════════════════════════════════╝

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe(getter, default=None):
    try:
        v = getter()
        return v if v is not None else default
    except Exception:
        return default


def _alignment_name(align) -> Optional[str]:
    if align is None:
        return None
    try:
        return _ALIGNMENT_NAMES.get(int(align), str(align))
    except Exception:
        return str(align)


def _color_to_hex(color) -> Optional[str]:
    """Conversion robuste : RGB direct, ou theme color, ou None."""
    if color is None:
        return None
    try:
        if color.rgb is not None:
            return f"#{color.rgb}"
    except Exception:
        pass
    try:
        if color.theme_color is not None:
            return f"theme:{color.theme_color}"
    except Exception:
        pass
    return None


def _emu_to_pt(emu) -> Optional[float]:
    """English Metric Units (1 pt = 12700 EMU)."""
    if emu is None:
        return None
    try:
        return round(int(emu) / 12700.0, 2)
    except Exception:
        return None


def _shape_type_name(shape) -> str:
    """Type de shape lisible (TEXT_BOX, PICTURE, TABLE, AUTO_SHAPE, ...)."""
    try:
        st = shape.shape_type
        if st is None:
            return "UNKNOWN"
        # MSO_SHAPE_TYPE est une enum — on prend le nom
        return str(st).split('.')[-1].split(' ')[0]
    except Exception:
        return "UNKNOWN"


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 3. EXTRACTORS                                                              ║
# ╚════════════════════════════════════════════════════════════════════════════╝

def _extract_run(run, slide_idx: int, shape_idx: int, para_idx: int, run_idx: int) -> dict:
    """Extraction COMPLÈTE des propriétés d'un run (= span PPTX)."""
    font = run.font
    return {
        "span_id":          f"pp_{slide_idx}_{shape_idx}_{para_idx}_{run_idx}",
        "slide_index":      slide_idx,
        "shape_index":      shape_idx,
        "paragraph_index":  para_idx,
        "run_index":        run_idx,
        "text":             run.text or "",
        "char_count":       len(run.text or ""),
        # Font
        "font_name":        _safe(lambda: font.name, ""),
        "font_size_pt":     _safe(lambda: font.size.pt if font.size else None),
        "bold":             _safe(lambda: bool(font.bold) if font.bold is not None else False, False),
        "italic":           _safe(lambda: bool(font.italic) if font.italic is not None else False, False),
        "underline":        _safe(lambda: bool(font.underline) if font.underline is not None else False, False),
        "color":            _color_to_hex(font.color) if font.color is not None else None,
        # Hyperlink (pptx)
        "hyperlink":        _safe(lambda: run.hyperlink.address if run.hyperlink and run.hyperlink.address else None),
    }


def _extract_paragraph(para, slide_idx: int, shape_idx: int, para_idx: int) -> dict:
    """Extraction d'un paragraphe (texte concaténé + alignement + niveau)."""
    text = para.text or ""
    return {
        "slide_index":      slide_idx,
        "shape_index":      shape_idx,
        "paragraph_index":  para_idx,
        "text":             text,
        "char_count":       len(text),
        "level":            _safe(lambda: para.level, 0) or 0,
        "alignment":        _alignment_name(_safe(lambda: para.alignment)),
        "n_runs":           len(para.runs),
    }


def _extract_image(shape, slide_idx: int, shape_idx: int, image_counter: int) -> dict:
    """Métadonnées d'une image embarquée."""
    return {
        "image_index":  image_counter,
        "slide_index":  slide_idx,
        "shape_index":  shape_idx,
        "name":         _safe(lambda: shape.name, ""),
        "width_pt":     _emu_to_pt(_safe(lambda: shape.width)),
        "height_pt":    _emu_to_pt(_safe(lambda: shape.height)),
        "left_pt":      _emu_to_pt(_safe(lambda: shape.left)),
        "top_pt":       _emu_to_pt(_safe(lambda: shape.top)),
    }


def _extract_table(shape, slide_idx: int, shape_idx: int, table_counter: int) -> dict:
    """Métadonnées + contenu d'une table."""
    table = shape.table
    rows = list(table.rows)
    n_rows = len(rows)
    n_cols = len(rows[0].cells) if n_rows else 0
    cells = [[cell.text for cell in row.cells] for row in rows]
    return {
        "table_index":  table_counter,
        "slide_index":  slide_idx,
        "shape_index":  shape_idx,
        "n_rows":       n_rows,
        "n_cols":       n_cols,
        "cells":        cells,
        "n_cells_with_text": sum(1 for row in cells for c in row if c.strip()),
    }


def _extract_shape(shape, slide_idx: int, shape_idx: int) -> dict:
    """Métadonnées d'une shape (sans son contenu détaillé)."""
    return {
        "slide_index":   slide_idx,
        "shape_index":   shape_idx,
        "shape_type":    _shape_type_name(shape),
        "name":          _safe(lambda: shape.name, ""),
        "has_text":      _safe(lambda: shape.has_text_frame, False),
        "has_table":     _safe(lambda: shape.has_table, False),
        "is_picture":    _safe(lambda: shape.shape_type == MSO_SHAPE_TYPE.PICTURE, False),
        "left_pt":       _emu_to_pt(_safe(lambda: shape.left)),
        "top_pt":        _emu_to_pt(_safe(lambda: shape.top)),
        "width_pt":      _emu_to_pt(_safe(lambda: shape.width)),
        "height_pt":     _emu_to_pt(_safe(lambda: shape.height)),
    }


def _extract_slide(slide, slide_idx: int, n_shapes: int, n_runs: int, n_images: int, n_tables: int) -> dict:
    """Métadonnées d'une slide."""
    return {
        "slide_index":      slide_idx,
        "layout_name":      _safe(lambda: slide.slide_layout.name, ""),
        "n_shapes":         n_shapes,
        "n_text_runs":      n_runs,
        "n_images":         n_images,
        "n_tables":         n_tables,
        "has_notes":        _safe(lambda: slide.has_notes_slide and bool(slide.notes_slide.notes_text_frame.text.strip()), False),
        "notes_text":       _safe(lambda: slide.notes_slide.notes_text_frame.text if slide.has_notes_slide else "", ""),
    }


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 4. METADATA & SYNTHESE                                                     ║
# ╚════════════════════════════════════════════════════════════════════════════╝

def _extract_doc_metadata(prs: Presentation) -> dict:
    """Properties core du presentation."""
    cp = prs.core_properties
    return {
        "title":              cp.title or "",
        "author":             cp.author or "",
        "last_modified_by":   cp.last_modified_by or "",
        "subject":            cp.subject or "",
        "keywords":           cp.keywords or "",
        "category":           cp.category or "",
        "comments":           cp.comments or "",
        "revision":           cp.revision,
        "created":            cp.created.isoformat() if cp.created else None,
        "modified":           cp.modified.isoformat() if cp.modified else None,
        "language":           cp.language or "",
    }


def _detect_source_tool(metadata: dict) -> str:
    """Outil ayant produit le .pptx (heuristique sur metadata)."""
    blob = " ".join([
        (metadata.get("author") or ""),
        (metadata.get("last_modified_by") or ""),
    ]).lower()
    if "libreoffice" in blob or "openoffice" in blob:
        return "LibreOffice Impress"
    if "google" in blob:
        return "Google Slides"
    if "keynote" in blob:
        return "Apple Keynote"
    if "wps" in blob:
        return "WPS Presentation"
    if metadata.get("author") or metadata.get("last_modified_by") or metadata.get("created"):
        return "Microsoft PowerPoint"
    return "Unknown"


def _build_doc_summary(
    pptx_path: Path,
    doc_hash: str,
    metadata: dict,
    slides: list[dict],
    runs: list[dict],
    images: list[dict],
    tables: list[dict],
    prs: Presentation,
) -> dict:
    """JSON synthèse au niveau document."""
    total_chars = sum(r["char_count"] for r in runs)
    n_runs_bold = sum(1 for r in runs if r["bold"])
    n_runs_italic = sum(1 for r in runs if r["italic"])
    n_runs_with_color = sum(1 for r in runs if r["color"])
    has_notes = any(s["has_notes"] for s in slides)

    # Distribution des layouts
    layout_counts: dict[str, int] = {}
    for s in slides:
        ln = s["layout_name"] or "(no layout)"
        layout_counts[ln] = layout_counts.get(ln, 0) + 1

    return {
        "doc_hash":               doc_hash,
        "file_size_bytes":        pptx_path.stat().st_size,
        "n_slides":               len(slides),
        "n_shapes":               sum(s["n_shapes"] for s in slides),
        "n_text_runs":            len(runs),
        "n_images":               len(images),
        "n_tables":               len(tables),
        "total_char_count":       total_chars,
        # Source / metadata
        "source_tool":            _detect_source_tool(metadata),
        "metadata":               metadata,
        # Signaux structurels
        "has_speaker_notes":      has_notes,
        "n_runs_bold":            n_runs_bold,
        "n_runs_italic":          n_runs_italic,
        "n_runs_with_color":      n_runs_with_color,
        # Distribution layouts (top 10)
        "layout_counts":          dict(sorted(layout_counts.items(), key=lambda kv: -kv[1])[:10]),
        # Geometry de la presentation
        "slide_width_pt":         _emu_to_pt(prs.slide_width),
        "slide_height_pt":        _emu_to_pt(prs.slide_height),
        # Recommandation pipeline aval
        "recommended_strategy":   "use_native_extraction",   # un .pptx est toujours extractible nativement
        # Méta-info de l'analyse
        "analyzed_at":            datetime.now().isoformat(),
        "parser_version":         "1.0.0",
    }


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 5. POINT D'ENTRÉE — parse_pptx                                             ║
# ╚════════════════════════════════════════════════════════════════════════════╝

def parse_pptx(pptx_path) -> dict:
    """
    Parser un .pptx en 6 sorties : slide_df, shape_df, paragraph_df, runs_df,
    image_df, table_df, doc_summary. Une seule ouverture python-pptx.
    """
    pptx_path = Path(pptx_path)
    doc_hash = _sha256(pptx_path)
    prs = Presentation(str(pptx_path))

    slides_meta:    list[dict] = []
    shapes:         list[dict] = []
    paragraphs:     list[dict] = []
    runs:           list[dict] = []
    images:         list[dict] = []
    tables:         list[dict] = []

    image_counter = 0
    table_counter = 0

    for slide_idx, slide in enumerate(prs.slides):
        slide_runs = 0
        slide_images = 0
        slide_tables = 0
        slide_shapes = list(slide.shapes)

        for shape_idx, shape in enumerate(slide_shapes):
            shapes.append(_extract_shape(shape, slide_idx, shape_idx))

            # Texte (si shape a un text_frame)
            if _safe(lambda: shape.has_text_frame, False):
                tf = shape.text_frame
                for para_idx, para in enumerate(tf.paragraphs):
                    paragraphs.append(_extract_paragraph(para, slide_idx, shape_idx, para_idx))
                    for run_idx, run in enumerate(para.runs):
                        runs.append(_extract_run(run, slide_idx, shape_idx, para_idx, run_idx))
                        slide_runs += 1

            # Image
            if _safe(lambda: shape.shape_type == MSO_SHAPE_TYPE.PICTURE, False):
                images.append(_extract_image(shape, slide_idx, shape_idx, image_counter))
                image_counter += 1
                slide_images += 1

            # Table
            if _safe(lambda: shape.has_table, False):
                tables.append(_extract_table(shape, slide_idx, shape_idx, table_counter))
                table_counter += 1
                slide_tables += 1

        slides_meta.append(_extract_slide(slide, slide_idx, len(slide_shapes), slide_runs, slide_images, slide_tables))

    metadata = _extract_doc_metadata(prs)

    slide_df     = pd.DataFrame(slides_meta)
    shape_df     = pd.DataFrame(shapes)
    paragraph_df = pd.DataFrame(paragraphs)
    runs_df      = pd.DataFrame(runs)
    image_df     = pd.DataFrame(images)
    table_df     = pd.DataFrame([{k: v for k, v in t.items() if k != "cells"} for t in tables])

    # PK uniforme : doc_hash en première colonne
    for df in (slide_df, shape_df, paragraph_df, runs_df, image_df, table_df):
        if not df.empty:
            df.insert(0, "doc_hash", doc_hash)

    doc_summary = _build_doc_summary(
        pptx_path, doc_hash, metadata, slides_meta, runs, images, tables, prs,
    )

    return {
        "slide_df":      slide_df,
        "shape_df":      shape_df,
        "paragraph_df":  paragraph_df,
        "runs_df":       runs_df,
        "image_df":      image_df,
        "table_df":      table_df,
        "doc_summary":   doc_summary,
        # Bonus utiles : cellules de tables non aplaties
        "tables_raw":    tables,
    }


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 6. CLI minimal                                                             ║
# ╚════════════════════════════════════════════════════════════════════════════╝

if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 2:
        print("Usage: python parse_pptx.py <pptx_path>", file=sys.stderr)
        sys.exit(1)

    result = parse_pptx(sys.argv[1])
    s = result["doc_summary"]
    print(json.dumps(s, indent=2, ensure_ascii=False, default=str))
    print()
    print(f"slides     : {len(result['slide_df'])}")
    print(f"shapes     : {len(result['shape_df'])}")
    print(f"runs       : {len(result['runs_df'])}")
    print(f"images     : {len(result['image_df'])}")
    print(f"tables     : {len(result['table_df'])}")

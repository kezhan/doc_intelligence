"""
TODO-005 — Embedded image extraction from native PDFs
TODO-007 — Decision function: should this image be processed by LLM?
TODO-010 — Full PDF extraction with style metadata (for translation pipeline)
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import pandas as pd
from PIL import Image


# ── TODO-005 ─────────────────────────────────────────────────────────────────

def extract_text_dataframe(pdf_path: str | Path) -> pd.DataFrame:
    """
    Standard parsing output: one row per text line.

    Columns: page, line, text, x0, y0, x1, y1, block_no
    """
    rows: list[dict[str, Any]] = []

    with fitz.open(str(pdf_path)) as doc:
        for page_num, page in enumerate(doc, start=1):
            blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
            line_no = 0
            for block in blocks:
                if block.get("type") != 0:  # skip image blocks
                    continue
                for line in block.get("lines", []):
                    text = " ".join(span["text"] for span in line["spans"]).strip()
                    if not text:
                        continue
                    bbox = line["bbox"]
                    rows.append({
                        "page": page_num,
                        "line": line_no,
                        "text": text,
                        "x0": round(bbox[0], 2),
                        "y0": round(bbox[1], 2),
                        "x1": round(bbox[2], 2),
                        "y1": round(bbox[3], 2),
                        "block_no": block["number"],
                    })
                    line_no += 1

    return pd.DataFrame(rows)


def extract_images_dataframe(
    pdf_path: str | Path,
    output_dir: str | Path | None = None,
    *,
    deduplicate: bool = True,
) -> pd.DataFrame:
    """
    TODO-005 — Extract embedded images into a parallel DataFrame.

    Columns: id, page, bbox, format, width, height, hash, path
    Deduplication: images with the same hash (e.g. repeated logos) are stored once.
    """
    if output_dir is not None:
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    img_id = 0

    with fitz.open(str(pdf_path)) as doc:
        for page_num, page in enumerate(doc, start=1):
            for img_info in page.get_images(full=True):
                xref = img_info[0]
                base_img = doc.extract_image(xref)
                img_bytes = base_img["image"]
                img_hash = hashlib.md5(img_bytes).hexdigest()

                if deduplicate and img_hash in seen_hashes:
                    continue
                seen_hashes.add(img_hash)

                pil_img = Image.open(io.BytesIO(img_bytes))
                fmt = base_img["ext"]

                saved_path: str | None = None
                if output_dir is not None:
                    saved_path = str(Path(output_dir) / f"img_{img_hash[:12]}.{fmt}")
                    pil_img.save(saved_path)

                # Approximate bbox from page image list
                bbox = _get_image_bbox(page, xref)

                rows.append({
                    "id": img_id,
                    "page": page_num,
                    "x0": round(bbox[0], 2) if bbox else None,
                    "y0": round(bbox[1], 2) if bbox else None,
                    "x1": round(bbox[2], 2) if bbox else None,
                    "y1": round(bbox[3], 2) if bbox else None,
                    "format": fmt,
                    "width": pil_img.width,
                    "height": pil_img.height,
                    "hash": img_hash,
                    "path": saved_path,
                })
                img_id += 1

    return pd.DataFrame(rows)


# ── TODO-007 ─────────────────────────────────────────────────────────────────

@dataclass
class ImageDecision:
    """Output contract for TODO-007."""
    should_process: bool
    reason: str


def should_process_image(image: str | Path | bytes) -> ImageDecision:
    """
    TODO-007 — Fast heuristic gate: should this image be sent to an LLM?

    Avoids expensive LLM calls for decorative/trivial images.
    """
    if isinstance(image, (str, Path)):
        img = Image.open(str(image))
    else:
        img = Image.open(io.BytesIO(image))

    w, h = img.size

    if w < 30 or h < 30:
        return ImageDecision(False, "too_small")

    aspect = max(w, h) / min(w, h) if min(w, h) > 0 else 99
    if aspect > 20:
        return ImageDecision(False, "degenerate_aspect_ratio")

    complexity = _visual_complexity(img)
    if complexity < 0.02:
        return ImageDecision(False, "low_visual_complexity")

    # Couleurs quasi-uniformes ET faible complexité → décoration
    if img.mode in ("RGB", "RGBA", "P") and complexity < 0.15:
        rgb = img.convert("RGB")
        colors = rgb.getcolors(maxcolors=256 * 256 * 256)
        if colors and len(colors) < 8:
            return ImageDecision(False, "nearly_uniform_color")

    return ImageDecision(True, "passed_all_heuristics")


# ── TODO-010 ─────────────────────────────────────────────────────────────────

def extract_full_with_style(pdf_path: str | Path) -> pd.DataFrame:
    """
    TODO-010 — Enriched extraction including font, size, color, orientation, bbox.

    Required for the translation pipeline where layout must be reconstructed.
    Columns: page, line, span_id, text, font, size, color, bold, italic,
             x0, y0, x1, y1, orientation
    """
    rows: list[dict[str, Any]] = []
    span_id = 0

    with fitz.open(str(pdf_path)) as doc:
        for page_num, page in enumerate(doc, start=1):
            blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
            line_no = 0

            for block in blocks:
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        if not text:
                            continue
                        flags = span.get("flags", 0)
                        color_int = span.get("color", 0)
                        color_hex = f"#{color_int:06x}" if color_int else "#000000"
                        bbox = span["bbox"]

                        rows.append({
                            "page": page_num,
                            "line": line_no,
                            "span_id": f"s{span_id}",
                            "text": text,
                            "font": span.get("font", ""),
                            "size": round(span.get("size", 0), 2),
                            "color": color_hex,
                            "bold": bool(flags & 2**4),
                            "italic": bool(flags & 2**1),
                            "x0": round(bbox[0], 2),
                            "y0": round(bbox[1], 2),
                            "x1": round(bbox[2], 2),
                            "y1": round(bbox[3], 2),
                            "orientation": _line_orientation(line),
                        })
                        span_id += 1
                    line_no += 1

    return pd.DataFrame(rows)


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_image_bbox(page: fitz.Page, xref: int) -> tuple[float, ...] | None:
    for img in page.get_image_info(xrefs=True):
        if img.get("xref") == xref:
            return img["bbox"]
    return None


def _visual_complexity(img: Image.Image) -> float:
    """Rough measure of image complexity via pixel variance."""
    import numpy as np
    gray = img.convert("L")
    arr = np.array(gray, dtype=float)
    if arr.size == 0:
        return 0.0
    return float(arr.std() / 255)


def _line_orientation(line: dict[str, Any]) -> str:
    dir_vec = line.get("dir", (1, 0))
    x, y = dir_vec
    if abs(x) > abs(y):
        return "horizontal"
    return "vertical"

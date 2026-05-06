"""
TODO-001 — PDF type detection via metadata + content analysis
TODO-002 — Scanned PDF without text layer detection
TODO-003 — Scanned PDF with degraded text layer detection
TODO-004 — Native vs hybrid PDF detection

ZERO LLM — classification entièrement heuristique/règles.

Stratégie en 3 niveaux :
  Niveau 1 — Métadonnées (creator/producer) : rapide, fiable si présentes
  Niveau 2 — Analyse de contenu (ratio image/texte, taille page, densité blocs)
  Niveau 3 — Signaux scanner (créateur OCR, couverture image pleine page)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF


# ── Types de sortie ───────────────────────────────────────────────────────────

class PDFCategory(str, Enum):
    WORD_NATIVE  = "word_native"   # Généré depuis Word / LibreOffice
    DESIGN_TOOL  = "design_tool"   # Photoshop, Illustrator, InDesign, Figma…
    SCANNED      = "scanned"       # Document scanné (image, pas de texte natif)
    OTHER        = "other"         # PDF natif non Word et non design


@dataclass
class PageMetrics:
    """Métriques extraites sur une page."""
    width: float
    height: float
    char_count: int
    image_count: int
    image_area_ratio: float   # surface images / surface page
    block_count: int          # blocs de texte
    font_names: list[str]
    has_full_page_image: bool  # image couvrant >85% de la page


@dataclass
class PDFClassification:
    """Output contract — TODO-001."""
    category: PDFCategory
    creator: str | None
    producer: str | None
    page_count: int
    confidence: float          # 0.0 → 1.0
    signals: list[str]         # traces des règles déclenchées
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScannedNoTextResult:
    """Output contract — TODO-002."""
    is_scanned_no_text: bool
    image_page_count: int
    text_page_count: int
    text_image_ratio: float


@dataclass
class ScannedWithTextResult:
    """Output contract — TODO-003."""
    is_scanned_with_text: bool
    text_quality_score: float   # 0.0 (illisible) → 1.0 (propre)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class NativeTextResult:
    """Output contract — TODO-004."""
    is_native_text: bool
    coverage_ratio: float


# ── Signaux métadonnées ───────────────────────────────────────────────────────

_WORD_META = frozenset({
    "microsoft word", "word", "libreoffice writer", "openoffice writer",
    "wps writer", "wps office", "google docs",
})
_DESIGN_META = frozenset({
    "adobe photoshop", "adobe illustrator", "adobe indesign",
    "figma", "sketch", "canva", "affinity publisher", "affinity designer",
    "coreldraw", "inkscape",
})
_SCANNER_META = frozenset({
    "scanner", "scan", "xerox", "hp scanjet", "epson scan", "canon scan",
    "acrobat capture", "readiris", "nuance", "finereader", "abbyy",
    "paperstream", "kofax",
})

# Pages A4 et Letter en points (±5 % de tolérance)
_STANDARD_PAGE_SIZES = [
    (595, 842),   # A4
    (612, 792),   # Letter US
    (420, 595),   # A5
    (842, 1191),  # A3
]
_SIZE_TOLERANCE = 0.05

_MIN_CHARS_PER_PAGE    = 50
_QUALITY_THRESHOLD     = 0.60
_OCR_ARTIFACT_CHARS    = set("@#$%^&*[]{}|\\<>~`")
_DESIGN_IMAGE_RATIO    = 0.55   # >55% de la page couvert par des images → design tool
_DESIGN_MAX_CHARS      = 120    # peu de caractères malgré du contenu → design tool
_SCANNED_IMAGE_RATIO   = 0.80   # >80% de la page = image plein format → scanné


def classify_pdf(pdf_path: str | Path) -> PDFClassification:
    """
    TODO-001 — Classifier le PDF en word_native / design_tool / scanned / other.

    Input  : chemin d'un fichier PDF
    Output : PDFClassification (catégorie + confiance + traces)

    Pas de LLM. Trois niveaux successifs :
      N1 Métadonnées  → word ou design si creator/producer reconnu
      N2 Contenu page → ratio image/texte, densité blocs, taille page
      N3 Signaux scan → créateur OCR, pages entièrement en image
    """
    with fitz.open(str(pdf_path)) as doc:
        meta        = doc.metadata or {}
        creator     = (meta.get("creator")  or "").lower().strip()
        producer    = (meta.get("producer") or "").lower().strip()
        page_count  = doc.page_count
        signals: list[str] = []

        # ── N1 : Métadonnées ─────────────────────────────────────────────────
        if _meta_matches(creator, producer, _WORD_META):
            signals.append("meta:word_creator")
            category, confidence = PDFCategory.WORD_NATIVE, 0.95

        elif _meta_matches(creator, producer, _DESIGN_META):
            signals.append("meta:design_creator")
            category, confidence = PDFCategory.DESIGN_TOOL, 0.95

        elif _meta_matches(creator, producer, _SCANNER_META):
            signals.append("meta:scanner_creator")
            category, confidence = PDFCategory.SCANNED, 0.90

        else:
            # ── N2 & N3 : Analyse de contenu ─────────────────────────────────
            pages_metrics = [_analyze_page(page) for page in doc]
            category, confidence, content_signals = _classify_by_content(pages_metrics)
            signals.extend(content_signals)

    return PDFClassification(
        category   = category,
        creator    = meta.get("creator"),
        producer   = meta.get("producer"),
        page_count = page_count,
        confidence = confidence,
        signals    = signals,
        metadata   = {k: v for k, v in meta.items() if v},
    )


# ── TODO-002 ──────────────────────────────────────────────────────────────────

def detect_scanned_no_text(pdf_path: str | Path) -> ScannedNoTextResult:
    """
    TODO-002 — Identifier les PDF où chaque page est une image sans couche texte.

    Input  : chemin PDF
    Output : ScannedNoTextResult (booléen + métriques)
    """
    with fitz.open(str(pdf_path)) as doc:
        image_pages = 0
        text_pages  = 0
        for page in doc:
            if len(page.get_text("text").strip()) < _MIN_CHARS_PER_PAGE:
                image_pages += 1
            else:
                text_pages += 1

    total = image_pages + text_pages
    return ScannedNoTextResult(
        is_scanned_no_text = (image_pages == total and total > 0),
        image_page_count   = image_pages,
        text_page_count    = text_pages,
        text_image_ratio   = text_pages / total if total else 0.0,
    )


# ── TODO-003 ──────────────────────────────────────────────────────────────────

def detect_scanned_with_text(pdf_path: str | Path) -> ScannedWithTextResult:
    """
    TODO-003 — Détecter les PDFs scannés avec une couche OCR dégradée.

    Un PDF scanné réocérisé a du texte, mais de mauvaise qualité :
    caractères parasites, faibles séquences alphabétiques, incohérences.

    Input  : chemin PDF
    Output : ScannedWithTextResult (booléen + score qualité 0→1)
    """
    with fitz.open(str(pdf_path)) as doc:
        page_scores = [
            _text_quality_score(page.get_text("text").strip())
            for page in doc
        ]

    if not page_scores:
        return ScannedWithTextResult(is_scanned_with_text=False, text_quality_score=1.0)

    avg = sum(page_scores) / len(page_scores)
    # Zone grise : texte présent mais qualité insuffisante = OCR dégradé
    is_scanned = 0.05 < avg < _QUALITY_THRESHOLD

    return ScannedWithTextResult(
        is_scanned_with_text = is_scanned,
        text_quality_score   = round(avg, 3),
        details = {"page_scores": [round(s, 3) for s in page_scores]},
    )


# ── TODO-004 ──────────────────────────────────────────────────────────────────

def detect_native_text(pdf_path: str | Path) -> NativeTextResult:
    """
    TODO-004 — Déterminer si le texte est natif (sans OCR nécessaire).

    Input  : chemin PDF
    Output : NativeTextResult (booléen + ratio de couverture)
    """
    with fitz.open(str(pdf_path)) as doc:
        total        = doc.page_count
        native_pages = sum(
            1 for page in doc
            if (
                len(page.get_text("text").strip()) >= _MIN_CHARS_PER_PAGE
                and _text_quality_score(page.get_text("text").strip()) >= _QUALITY_THRESHOLD
            )
        )

    coverage = native_pages / total if total else 0.0
    return NativeTextResult(
        is_native_text  = coverage >= 0.80,
        coverage_ratio  = round(coverage, 3),
    )


# ── Analyse de page (N2 — sans LLM) ──────────────────────────────────────────

def _analyze_page(page: fitz.Page) -> PageMetrics:
    """Extraire les métriques d'une page : texte, images, taille."""
    rect      = page.rect
    page_area = rect.width * rect.height or 1

    # Texte
    text        = page.get_text("text").strip()
    char_count  = len(text)

    # Blocs texte
    blocks     = page.get_text("dict")["blocks"]
    text_blocks = [b for b in blocks if b.get("type") == 0]
    block_count = len(text_blocks)

    # Polices
    font_names: list[str] = []
    for b in text_blocks:
        for line in b.get("lines", []):
            for span in line.get("spans", []):
                fn = span.get("font", "")
                if fn and fn not in font_names:
                    font_names.append(fn)

    # Images
    images        = page.get_images(full=True)
    image_count   = len(images)
    image_area    = 0.0
    has_full_page = False

    for img_info in page.get_image_info():
        bbox = img_info.get("bbox")
        if bbox:
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            area = w * h
            image_area += area
            ratio = area / page_area
            if ratio > 0.85:
                has_full_page = True

    return PageMetrics(
        width             = rect.width,
        height            = rect.height,
        char_count        = char_count,
        image_count       = image_count,
        image_area_ratio  = min(image_area / page_area, 1.0),
        block_count       = block_count,
        font_names        = font_names,
        has_full_page_image = has_full_page,
    )


def _classify_by_content(
    pages: list[PageMetrics],
) -> tuple[PDFCategory, float, list[str]]:
    """
    N2 + N3 — Classifier par analyse de contenu quand les métadonnées sont absentes.

    Règles appliquées (sans LLM) :
      - Scanned     : pages avec image plein format, très peu de texte
      - Design tool : image_area_ratio élevé + peu de blocs texte structurés
      - Word native : taille page standard + polices cohérentes + texte dense
      - Other       : fallback
    """
    if not pages:
        return PDFCategory.OTHER, 0.5, ["no_pages"]

    signals: list[str] = []

    n_pages       = len(pages)
    avg_chars     = sum(p.char_count       for p in pages) / n_pages
    avg_img_ratio = sum(p.image_area_ratio for p in pages) / n_pages
    avg_blocks    = sum(p.block_count      for p in pages) / n_pages
    full_page_img = sum(1 for p in pages if p.has_full_page_image)
    full_ratio    = full_page_img / n_pages

    # Polices uniques dans tout le document
    all_fonts = {f for p in pages for f in p.font_names}
    # Pages à taille standard
    standard_pages = sum(1 for p in pages if _is_standard_size(p.width, p.height))
    standard_ratio = standard_pages / n_pages

    # ── Règle SCANNED (priorité haute) ───────────────────────────────────────
    if full_ratio >= 0.70 and avg_chars < _MIN_CHARS_PER_PAGE:
        signals.append(f"content:full_page_images={full_ratio:.0%}")
        signals.append(f"content:avg_chars={avg_chars:.0f}")
        return PDFCategory.SCANNED, 0.88, signals

    # ── Règle DESIGN TOOL ────────────────────────────────────────────────────
    # Image couvrant >55% de la page + peu de blocs texte = mise en page graphique
    if avg_img_ratio >= _DESIGN_IMAGE_RATIO and avg_blocks < 6:
        signals.append(f"content:image_area={avg_img_ratio:.0%}")
        signals.append(f"content:low_text_blocks={avg_blocks:.1f}")
        return PDFCategory.DESIGN_TOOL, 0.80, signals

    # Peu de texte malgré des images = design tool (Photoshop, affiche...)
    if avg_chars < _DESIGN_MAX_CHARS and avg_img_ratio > 0.30 and avg_blocks < 4:
        signals.append(f"content:sparse_text={avg_chars:.0f}chars")
        signals.append(f"content:image_present={avg_img_ratio:.0%}")
        return PDFCategory.DESIGN_TOOL, 0.72, signals

    # ── Règle WORD NATIVE ─────────────────────────────────────────────────────
    # Taille page standard + polices cohérentes (≤5) + texte dense
    if (
        standard_ratio >= 0.85
        and len(all_fonts) <= 8
        and avg_chars > 200
        and avg_blocks >= 3
    ):
        signals.append(f"content:standard_page={standard_ratio:.0%}")
        signals.append(f"content:font_diversity={len(all_fonts)}")
        signals.append(f"content:text_dense={avg_chars:.0f}chars")
        return PDFCategory.WORD_NATIVE, 0.70, signals

    signals.append("content:no_rule_matched")
    return PDFCategory.OTHER, 0.55, signals


# ── Helpers ───────────────────────────────────────────────────────────────────

def _meta_matches(creator: str, producer: str, signals: frozenset[str]) -> bool:
    return any(s in creator or s in producer for s in signals)


def _is_standard_size(w: float, h: float) -> bool:
    for sw, sh in _STANDARD_PAGE_SIZES:
        if (
            abs(w - sw) / sw <= _SIZE_TOLERANCE
            and abs(h - sh) / sh <= _SIZE_TOLERANCE
        ) or (
            abs(w - sh) / sh <= _SIZE_TOLERANCE
            and abs(h - sw) / sw <= _SIZE_TOLERANCE
        ):
            return True
    return False


def _text_quality_score(text: str) -> float:
    """Ratio mots propres / total — détecte le texte OCR dégradé. Sans LLM."""
    if not text:
        return 0.0
    words = text.split()
    if not words:
        return 0.0
    clean = sum(
        1 for w in words
        if len(w) >= 2
        and not any(c in _OCR_ARTIFACT_CHARS for c in w)
        and sum(c.isalpha() for c in w) / len(w) >= 0.6
    )
    return clean / len(words)

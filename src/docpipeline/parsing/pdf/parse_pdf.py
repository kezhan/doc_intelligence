"""
parse_pdf.py — Analyse complète d'un PDF en UNE seule ouverture fitz.

Point d'entrée unique : `parse_pdf(path)` renvoie 4 sorties prêtes à être
consommées en aval (LLM, indexation sémantique, base de données, API) :

    {
        "line_df":     pd.DataFrame,   # 1 ligne = 1 ligne de texte du PDF
        "image_df":    pd.DataFrame,   # 1 ligne = 1 image embarquée
        "page_df":     pd.DataFrame,   # 1 ligne = 1 page (page_type + flags)
        "doc_summary": dict,           # JSON synthèse au niveau document
    }

Toute la logique est ici (pas de dépendance vers d'autres fichiers internes) :

    1. Patterns metadata + outils         (Word / InDesign / CamScanner / ...)
    2. Lecture metadata + XMP             (read_metadata, parse_xmp)
    3. Normalisation + matching           (creator, producer, history)
    4. Décision catégorie source PDF      (word_native / design_tool / scanned / other)
    5. Inspection page-par-page           (fonts, texte natif, OCR, images, tables)
    6. Décision page_type + stratégie     (8 catégories + extraction_strategy)
    7. Score qualité OCR                  (ratio caractères de remplacement)
    8. Synthèse document                  (recommended_strategy, pages_needing_ocr)
    9. Matérialisation en DataFrames

Pas de classe, uniquement des fonctions pures + dataclasses. Une seule
ouverture fitz pour tout le pipeline (sauf la sous-fonction de TODO-001 qui
réutilise une 2ème ouverture rapide pour la lisibilité de la décision source ;
le coût en I/O est négligeable face au parsing des pages).
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import fitz
import pandas as pd


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 1. CONSTANTES                                                              ║
# ╚════════════════════════════════════════════════════════════════════════════╝

# ─── Catégorie source PDF (revendiquée par les metadata) ────────────────────

CATEGORY_WORD_NATIVE = "word_native"
CATEGORY_DESIGN_TOOL = "design_tool"
CATEGORY_SCANNED     = "scanned"
CATEGORY_OTHER       = "other"

# ─── page_type (mutuellement exclusif) ──────────────────────────────────────

PAGE_TYPE_NATIVE              = "native"
PAGE_TYPE_NATIVE_WITH_IMAGE   = "native_with_image"
PAGE_TYPE_SCANNED             = "scanned"
PAGE_TYPE_SCANNED_OCR_GOOD    = "scanned_ocr_good"
PAGE_TYPE_SCANNED_OCR_BAD     = "scanned_ocr_bad"
PAGE_TYPE_MIXED               = "mixed"
PAGE_TYPE_EMPTY               = "empty"
PAGE_TYPE_UNKNOWN             = "unknown"

# ─── extraction_strategy (routage pour le pipeline aval) ────────────────────

STRATEGY_NATIVE = "native"   # fitz direct
STRATEGY_OCR    = "ocr"      # OCR obligatoire
STRATEGY_HYBRID = "hybrid"   # texte natif + OCR sur images
STRATEGY_SKIP   = "skip"     # page vide

# ─── Seuils de décision ─────────────────────────────────────────────────────

_FULL_PAGE_THRESHOLD     = 0.85
_MIN_NATIVE_CHARS        = 30
_MIN_OCR_CHARS           = 50
_OCR_QUALITY_THRESHOLD   = 0.70
_DOC_AGGREGATION_RATIO   = 0.95


# ─── Patterns par catégorie (lowercase, normalisés) ─────────────────────────
# Format : (pattern, kind) — kind ∈ {"exact", "startswith", "contains", "regex"}

_WORD_NATIVE_PATTERNS = (
    ("microsoft word",      "contains"),
    ("microsoft® word",     "contains"),
    ("word for windows",    "contains"),
    ("word for mac",        "contains"),
    ("microsoft office word", "contains"),
    ("ms word",             "contains"),
    ("libreoffice",         "contains"),
    ("openoffice",          "contains"),
    ("staroffice",          "contains"),
    ("google docs",         "contains"),
    ("google",              "exact"),
    ("wps writer",          "contains"),
    ("wps office",          "contains"),
    ("kingsoft writer",     "contains"),
    ("onlyoffice",          "contains"),
    ("pages",               "exact"),
    (r"^pages \d",          "regex"),
    ("abiword",             "contains"),
    ("iwork",               "contains"),
)

_DESIGN_TOOL_PATTERNS = (
    ("adobe indesign",      "contains"),
    ("adobe photoshop",     "contains"),
    ("adobe illustrator",   "contains"),
    ("adobe acrobat",       "contains"),
    ("indesign",            "contains"),
    ("photoshop",           "contains"),
    ("illustrator",         "contains"),
    ("affinity publisher",  "contains"),
    ("affinity designer",   "contains"),
    ("affinity photo",      "contains"),
    ("figma",               "contains"),
    ("sketch",              "contains"),
    ("canva",               "contains"),
    ("coreldraw",           "contains"),
    ("corel draw",          "contains"),
    ("corel designer",      "contains"),
    ("inkscape",            "contains"),
    ("quarkxpress",         "contains"),
    ("scribus",             "contains"),
    ("microsoft powerpoint", "contains"),
    ("powerpoint",          "exact"),
    ("keynote",             "contains"),
    ("adobe xd",            "contains"),
)

_SCANNED_PATTERNS = (
    ("scanner",             "contains"),
    ("scansnap",            "contains"),
    ("hp scan",             "contains"),
    ("hp scanjet",          "contains"),
    ("hp digital sender",   "contains"),
    ("xerox",               "contains"),
    ("epson scan",          "contains"),
    ("epson workforce",     "contains"),
    ("canon",               "contains"),
    ("brother mfc",         "contains"),
    ("brother dcp",         "contains"),
    ("ricoh",               "contains"),
    ("kyocera",             "contains"),
    ("fujitsu",             "contains"),
    ("paperstream",         "contains"),
    ("kofax",               "contains"),
    ("acrobat capture",     "contains"),
    ("readiris",            "contains"),
    ("nuance",              "contains"),
    ("finereader",          "contains"),
    ("abbyy",               "contains"),
    ("tesseract",           "contains"),
    ("ocrmypdf",            "contains"),
    ("paperport",           "contains"),
    ("camscanner",          "contains"),
    ("adobe scan",          "contains"),
    ("office lens",         "contains"),
    ("microsoft lens",      "contains"),
    ("genius scan",         "contains"),
    ("scanbot",             "contains"),
    ("scannable",           "contains"),
    ("turboscan",           "contains"),
)

_GENERIC_PRODUCER_PATTERNS = (
    "acrobat distiller", "adobe pdf library", "pdfwriter",
    "ghostscript", "gpl ghostscript", "itext", "tcpdf", "fpdf",
    "reportlab", "wkhtmltopdf", "weasyprint", "prince",
    "chromium", "skia", "quartz pdfcontext", "macos quartz",
    "microsoft: print to pdf", "pdf-xchange", "pdfsharp", "pdfium",
)

# ─── Mapping pattern → nom canonique d'outil ────────────────────────────────
# Du plus spécifique au plus générique (les producers génériques en queue).

_TOOL_NAMES: tuple[tuple[str, str], ...] = (
    # Word native
    ("microsoft office word",  "Microsoft Word"),
    ("microsoft® word",        "Microsoft Word"),
    ("microsoft word",         "Microsoft Word"),
    ("word for windows",       "Microsoft Word"),
    ("word for mac",           "Microsoft Word"),
    ("ms word",                "Microsoft Word"),
    ("libreoffice",            "LibreOffice"),
    ("openoffice",             "OpenOffice"),
    ("staroffice",             "StarOffice"),
    ("google docs",            "Google Docs"),
    ("wps writer",             "WPS Writer"),
    ("wps office",             "WPS Office"),
    ("kingsoft writer",        "Kingsoft Writer"),
    ("onlyoffice",             "OnlyOffice"),
    ("abiword",                "AbiWord"),
    ("iwork",                  "Apple iWork"),
    ("apple pages",            "Apple Pages"),
    # Design
    ("adobe indesign",         "Adobe InDesign"),
    ("adobe photoshop",        "Adobe Photoshop"),
    ("adobe illustrator",      "Adobe Illustrator"),
    ("adobe xd",               "Adobe XD"),
    ("adobe acrobat",          "Adobe Acrobat"),
    ("indesign",               "Adobe InDesign"),
    ("photoshop",              "Adobe Photoshop"),
    ("illustrator",            "Adobe Illustrator"),
    ("affinity publisher",     "Affinity Publisher"),
    ("affinity designer",      "Affinity Designer"),
    ("affinity photo",         "Affinity Photo"),
    ("figma",                  "Figma"),
    ("sketch",                 "Sketch"),
    ("canva",                  "Canva"),
    ("coreldraw",              "CorelDRAW"),
    ("corel draw",             "CorelDRAW"),
    ("corel designer",         "Corel Designer"),
    ("inkscape",               "Inkscape"),
    ("quarkxpress",            "QuarkXPress"),
    ("scribus",                "Scribus"),
    ("microsoft powerpoint",   "Microsoft PowerPoint"),
    ("keynote",                "Apple Keynote"),
    # Scanners / OCR / mobile
    ("hp scanjet",             "HP ScanJet"),
    ("hp digital sender",      "HP Digital Sender"),
    ("hp scan",                "HP Scan"),
    ("scansnap",               "Fujitsu ScanSnap"),
    ("xerox",                  "Xerox"),
    ("epson workforce",        "Epson WorkForce"),
    ("epson scan",             "Epson Scan"),
    ("brother mfc",            "Brother MFC"),
    ("brother dcp",            "Brother DCP"),
    ("ricoh",                  "Ricoh"),
    ("kyocera",                "Kyocera"),
    ("paperstream",            "Fujitsu PaperStream"),
    ("fujitsu",                "Fujitsu"),
    ("kofax",                  "Kofax"),
    ("acrobat capture",        "Adobe Acrobat Capture"),
    ("readiris",               "Readiris"),
    ("finereader",             "ABBYY FineReader"),
    ("abbyy",                  "ABBYY"),
    ("nuance",                 "Nuance"),
    ("tesseract",              "Tesseract"),
    ("ocrmypdf",               "OCRmyPDF"),
    ("paperport",              "PaperPort"),
    ("camscanner",             "CamScanner"),
    ("adobe scan",             "Adobe Scan"),
    ("microsoft lens",         "Microsoft Lens"),
    ("office lens",            "Microsoft Office Lens"),
    ("genius scan",            "Genius Scan"),
    ("scanbot",                "Scanbot"),
    ("scannable",              "Scannable"),
    ("turboscan",              "TurboScan"),
    ("canon",                  "Canon"),
    ("scanner",                "Generic scanner"),
    # Generic producers (en queue : ne matchent que si rien d'applicatif n'a matché)
    ("acrobat distiller",      "Adobe Acrobat Distiller"),
    ("adobe pdf library",      "Adobe PDF Library"),
    ("microsoft: print to pdf", "Microsoft Print to PDF"),
    ("gpl ghostscript",        "Ghostscript"),
    ("ghostscript",            "Ghostscript"),
    ("itext",                  "iText"),
    ("tcpdf",                  "TCPDF"),
    ("fpdf",                   "FPDF"),
    ("reportlab",              "ReportLab"),
    ("wkhtmltopdf",            "wkhtmltopdf"),
    ("weasyprint",             "WeasyPrint"),
    ("prince",                 "Prince"),
    ("chromium",               "Chromium"),
    ("skia",                   "Chrome / Skia"),
    ("quartz pdfcontext",      "macOS Quartz"),
    ("macos quartz",           "macOS Quartz"),
    ("pdf-xchange",            "PDF-XChange"),
    ("pdfsharp",               "PDFsharp"),
    ("pdfium",                 "PDFium"),
)

_SCANNER_TOOL_NAMES: frozenset[str] = frozenset({
    "HP Scan", "HP ScanJet", "HP Digital Sender", "Fujitsu ScanSnap",
    "Xerox", "Epson Scan", "Epson WorkForce", "Brother MFC", "Brother DCP",
    "Ricoh", "Kyocera", "Fujitsu PaperStream", "Fujitsu", "Kofax",
    "Adobe Acrobat Capture", "Readiris", "ABBYY FineReader", "ABBYY",
    "Nuance", "Tesseract", "OCRmyPDF", "PaperPort", "CamScanner",
    "Adobe Scan", "Microsoft Lens", "Microsoft Office Lens",
    "Genius Scan", "Scanbot", "Scannable", "TurboScan", "Canon",
    "Generic scanner",
})
_SCANNER_PATTERNS: frozenset[str] = frozenset(
    pat for pat, name in _TOOL_NAMES if name in _SCANNER_TOOL_NAMES
)


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 2. DATACLASSES — contrat de sortie                                         ║
# ╚════════════════════════════════════════════════════════════════════════════╝

@dataclass
class LineInfo:
    page_num:    int
    line_num:    int
    span_id:     str                                          # format "p_<page>_<line>"
    text:        str
    bbox:        tuple[float, float, float, float]
    font_name:   str
    font_size:   float
    bold:        bool                                         # déduit des flags fitz
    italic:      bool                                         # déduit des flags fitz
    color:       str                                          # "#RRGGBB" ou ""
    is_invisible: bool                                        # rendu en mode invisible (couche OCR typique)


@dataclass
class ImageInfo:
    page_num:        int
    image_num:       int
    bbox:            tuple[float, float, float, float]
    width:           int
    height:          int
    coverage_ratio:  float


@dataclass
class TableInfo:
    page_num:    int
    table_num:   int
    bbox:        tuple[float, float, float, float]
    n_rows:      int
    n_cols:      int


@dataclass
class PageInfo:
    page_num:               int
    page_type:              str = PAGE_TYPE_UNKNOWN
    has_text:               bool = False
    has_native_text:        bool = False
    has_ocr_layer:          bool = False
    has_image:              bool = False
    has_full_page_image:    bool = False
    has_vector_table:       bool = False
    has_vector_graphics:    bool = False
    n_lines:                int = 0
    n_images:               int = 0
    n_fonts:                int = 0
    n_tables:               int = 0
    char_count:             int = 0
    native_char_count:      int = 0
    ocr_char_count:         int = 0
    drawing_count:          int = 0
    image_coverage_ratio:   float = 0.0
    text_quality_score:     Optional[float] = None
    page_width:             float = 0.0
    page_height:            float = 0.0
    rotation:               int = 0
    extraction_strategy:    str = STRATEGY_NATIVE
    tool:                   str = "Unknown"


@dataclass
class PDFInspection:
    pdf_hash:              str
    file_size:             int
    n_pages:               int
    pdf_version:           Optional[str] = None
    is_encrypted:          bool = False
    is_form_pdf:           bool = False
    metadata_raw:          dict = field(default_factory=dict)
    metadata_normalized:   dict = field(default_factory=dict)
    metadata_xmp:          dict = field(default_factory=dict)
    source_category:       str = CATEGORY_OTHER
    source_tool:           str = "Unknown"
    source_confidence:     float = 0.0
    source_signals:        list[str] = field(default_factory=list)
    pages:                 list[PageInfo] = field(default_factory=list)
    lines:                 list[LineInfo] = field(default_factory=list)
    images:                list[ImageInfo] = field(default_factory=list)
    tables:                list[TableInfo] = field(default_factory=list)
    extracted_at:          Optional[datetime] = None
    fitz_version:          Optional[str] = None
    inspector_version:     str = "1.0.0"


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 3. METADATA — lecture, XMP, normalisation, matching                        ║
# ╚════════════════════════════════════════════════════════════════════════════╝

_XMP_CREATOR_TOOL_RE  = re.compile(r"<xmp:CreatorTool[^>]*>(.*?)</xmp:CreatorTool>", re.IGNORECASE | re.DOTALL)
_XMP_PRODUCER_RE      = re.compile(r"<pdf:Producer[^>]*>(.*?)</pdf:Producer>",       re.IGNORECASE | re.DOTALL)
_XMP_TITLE_RE         = re.compile(r"<dc:title[^>]*>.*?<rdf:li[^>]*>(.*?)</rdf:li>", re.IGNORECASE | re.DOTALL)
_XMP_CREATOR_RE       = re.compile(r"<dc:creator[^>]*>.*?<rdf:li[^>]*>(.*?)</rdf:li>", re.IGNORECASE | re.DOTALL)
_XMP_HISTORY_AGENT_RE = re.compile(r"<stEvt:softwareAgent[^>]*>(.*?)</stEvt:softwareAgent>", re.IGNORECASE | re.DOTALL)

_VERSION_RE = re.compile(r"\s+\d[\d.]*(?:\s*\([^)]*\))?\s*$")
_PARENS_RE  = re.compile(r"\s*\([^)]*\)\s*$")


def _read_pdf_version(doc) -> Optional[str]:
    fmt = (doc.metadata or {}).get("format")
    if fmt:
        m = re.search(r"PDF\s+([\d.]+)", fmt, flags=re.IGNORECASE)
        if m:
            return m.group(1)
    for attr in ("pdf_version", "version"):
        try:
            v = getattr(doc, attr)
            if callable(v):
                v = v()
            if v:
                return str(v)
        except Exception:
            continue
    return None


def parse_xmp(xmp_xml: str) -> dict:
    """Extraire les champs XMP utiles (sans dépendance lxml)."""
    if not xmp_xml:
        return {}

    def _first(rx):
        m = rx.search(xmp_xml)
        return m.group(1).strip() if m else None

    history_agents = [a.strip() for a in _XMP_HISTORY_AGENT_RE.findall(xmp_xml)]
    return {
        "creator_tool":   _first(_XMP_CREATOR_TOOL_RE),
        "producer":       _first(_XMP_PRODUCER_RE),
        "title":          _first(_XMP_TITLE_RE),
        "creator":        _first(_XMP_CREATOR_RE),
        "history_agents": history_agents,
    }


def _normalize(value) -> str:
    """Lowercase, strip, normalisation des espaces (y compris insécables)."""
    if value is None:
        return ""
    s = str(value).strip().lower()
    s = s.replace("\xa0", " ").replace(" ", " ")
    return re.sub(r"\s+", " ", s)


def _strip_version(value: str) -> str:
    """Retirer parenthèses finales et numéros de version."""
    s = _PARENS_RE.sub("", value).strip()
    return _VERSION_RE.sub("", s).strip()


def normalize_metadata(metadata: dict) -> dict:
    """Construire un dict des champs textuels normalisés et prêts à matcher."""
    docinfo = metadata.get("docinfo", {}) or {}
    xmp     = metadata.get("xmp",     {}) or {}

    creator  = docinfo.get("creator")  or xmp.get("creator_tool") or ""
    producer = docinfo.get("producer") or xmp.get("producer")     or ""
    title    = docinfo.get("title")    or xmp.get("title")        or ""
    author   = docinfo.get("author")   or xmp.get("creator")      or ""

    # Dédupliquer les agents XMP (un PDF InDesign peut en répéter 200×)
    seen: set[str] = set()
    history_agents: list[str] = []
    for a in xmp.get("history_agents", []) or []:
        n = _normalize(a)
        if n and n not in seen:
            seen.add(n)
            history_agents.append(n)

    return {
        "creator":         _normalize(creator),
        "creator_no_ver":  _strip_version(_normalize(creator)),
        "producer":        _normalize(producer),
        "producer_no_ver": _strip_version(_normalize(producer)),
        "title":           _normalize(title),
        "author":          _normalize(author),
        "history_agents":  history_agents,
    }


def _matches_pattern(value: str, pattern: str, kind: str) -> bool:
    if not value:
        return False
    if kind == "exact":      return value == pattern
    if kind == "startswith": return value.startswith(pattern)
    if kind == "contains":   return pattern in value
    if kind == "regex":      return bool(re.search(pattern, value))
    return False


def _is_generic_producer(producer: str) -> bool:
    return any(p in producer for p in _GENERIC_PRODUCER_PATTERNS)


def _category_score(normalized: dict) -> dict:
    """
    Pour chaque catégorie, retourner score + signaux. Pondération :
      creator×3, producer×2, author/title×1, history_agents×1.
    """
    def _score(patterns):
        sigs, score = [], 0.0
        for v, weight, label in (
            (normalized["creator"],  3.0, "creator"),
            (normalized["producer"], 2.0, "producer"),
            (normalized["author"],   1.0, "author"),
            (normalized["title"],    1.0, "title"),
        ):
            if not v:
                continue
            for pat, kind in patterns:
                if _matches_pattern(v, pat, kind):
                    score += weight
                    sigs.append(f"{label}~{pat}")
                    break
        for agent in normalized["history_agents"]:
            for pat, kind in patterns:
                if _matches_pattern(agent, pat, kind):
                    score += 1.0
                    sigs.append(f"xmp_history~{pat}")
                    break
        return score, sigs

    word_score,    word_sigs    = _score(_WORD_NATIVE_PATTERNS)
    design_score,  design_sigs  = _score(_DESIGN_TOOL_PATTERNS)
    scanned_score, scanned_sigs = _score(_SCANNED_PATTERNS)

    return {
        CATEGORY_WORD_NATIVE: {"score": word_score,    "signals": word_sigs},
        CATEGORY_DESIGN_TOOL: {"score": design_score,  "signals": design_sigs},
        CATEGORY_SCANNED:     {"score": scanned_score, "signals": scanned_sigs},
    }


def _decide_source_category(scores: dict, normalized: dict) -> tuple[str, float, list[str]]:
    """Décider catégorie + confidence + signaux à partir des scores."""
    sorted_cats = sorted(scores.items(), key=lambda kv: kv[1]["score"], reverse=True)
    top_cat, top_data = sorted_cats[0]
    top_score = top_data["score"]
    second_score = sorted_cats[1][1]["score"] if len(sorted_cats) > 1 else 0.0

    if top_score >= 3.0 and (top_score - second_score) >= 2.0:
        return top_cat, 0.95, top_data["signals"]
    if top_score >= 3.0:
        return top_cat, 0.80, top_data["signals"] + sorted_cats[1][1]["signals"]
    if top_score >= 1.0:
        return top_cat, 0.65, top_data["signals"] + ["weak_match_only"]
    if _is_generic_producer(normalized["producer"]):
        return CATEGORY_OTHER, 0.55, [f"generic_producer:{normalized['producer']}"]
    if not any([normalized["creator"], normalized["producer"], normalized["author"], normalized["title"]]):
        return CATEGORY_OTHER, 0.30, ["no_metadata"]
    return CATEGORY_OTHER, 0.45, ["no_pattern_matched"]


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 4. DÉTECTION D'OUTIL (Adobe InDesign / CamScanner / Microsoft Word / ...)  ║
# ╚════════════════════════════════════════════════════════════════════════════╝

def _detect_tool(value: str) -> Optional[str]:
    """Renvoyer le nom canonique du premier outil reconnu dans value."""
    if not value:
        return None
    for pattern, name in _TOOL_NAMES:
        if pattern in value:
            return name
    return None


def _detect_page_tool(page_category: str, source_category: str, normalized: dict) -> str:
    """
    Inférer l'outil ayant produit la page.

      - Page héritant de la catégorie du doc → outil reconnu dans creator/producer.
      - Page scannée dans un doc non-scanné (image incrustée) → premier scanner
        identifié dans l'historique XMP, sinon "Unknown (embedded scan)".
      - Sinon → outil reconnu dans creator/producer, ou "Unknown".
    """
    creator  = normalized.get("creator", "")
    producer = normalized.get("producer", "")
    history  = normalized.get("history_agents", []) or []

    if page_category in (PAGE_TYPE_SCANNED, PAGE_TYPE_SCANNED_OCR_GOOD, PAGE_TYPE_SCANNED_OCR_BAD):
        if source_category != CATEGORY_SCANNED:
            for agent in history:
                if any(p in agent for p in _SCANNER_PATTERNS):
                    tool = _detect_tool(agent)
                    if tool:
                        return tool
            return "Unknown (embedded scan)"

    return _detect_tool(creator) or _detect_tool(producer) or "Unknown"


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 5. INSPECTOR — UNE seule ouverture fitz, collecte tous les faits           ║
# ╚════════════════════════════════════════════════════════════════════════════╝

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _max_image_coverage(image_infos: list[dict], page_area: float) -> float:
    """Plus grand ratio (surface bbox image / surface page)."""
    if not image_infos or not page_area:
        return 0.0
    max_r = 0.0
    for info in image_infos:
        bbox = info.get("bbox")
        if not bbox:
            continue
        area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
        ratio = area / page_area
        if ratio > max_r:
            max_r = ratio
    return max_r


def _is_invisible_span(span: dict) -> bool:
    """Span rendu en blanc pur (255,255,255) = couche OCR typique."""
    return span.get("color", 0) == 0xFFFFFF


def _font_flags_to_bold_italic(flags: int, font_name: str) -> tuple[bool, bool]:
    """
    fitz expose des flags bit-field sur chaque span :
        bit 4 (16) = bold ; bit 1 (2) = italic
    On combine avec une heuristique sur le nom de police (« Bold », « Italic »)
    parce que tous les PDFs ne renseignent pas correctement les flags.
    """
    bold   = bool(flags & 16) or any(tag in (font_name or "") for tag in ("Bold", "Black", "Heavy"))
    italic = bool(flags & 2)  or any(tag in (font_name or "") for tag in ("Italic", "Oblique"))
    return bold, italic


def _color_int_to_hex(color: int) -> str:
    """Couleur fitz (entier 24-bit RGB) → '#RRGGBB'."""
    if not isinstance(color, int):
        return ""
    return f"#{color:06X}"


def _collect_page_lines(page, page_num: int, start_line_num: int) -> tuple[list[LineInfo], int, int]:
    """Extraire les lignes d'une page. Retourne (lines, native_chars, ocr_chars)."""
    lines: list[LineInfo] = []
    native_chars = 0
    ocr_chars    = 0
    line_num     = start_line_num

    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:  # 0 = bloc texte (1 = image)
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            line_text = "".join(s.get("text", "") for s in spans)
            if not line_text.strip():
                continue
            invisible = any(_is_invisible_span(s) for s in spans)
            if invisible:
                ocr_chars += len(line_text)
            else:
                native_chars += len(line_text)

            # Style du premier span de la ligne (heuristique : la ligne est
            # généralement homogène ; pour un découpage finer, on aurait
            # 1 span par run, mais le contrat actuel = 1 ligne = 1 unité).
            first = spans[0]
            bold, italic = _font_flags_to_bold_italic(first.get("flags", 0), first.get("font", ""))
            color_hex = _color_int_to_hex(first.get("color", 0)) if not invisible else ""

            lines.append(LineInfo(
                page_num     = page_num,
                line_num     = line_num,
                span_id      = f"p_{page_num}_{line_num}",
                text         = line_text,
                bbox         = tuple(line.get("bbox", (0, 0, 0, 0))),
                font_name    = first.get("font", ""),
                font_size    = float(first.get("size", 0.0)),
                bold         = bold,
                italic       = italic,
                color        = color_hex,
                is_invisible = invisible,
            ))
            line_num += 1
    return lines, native_chars, ocr_chars


def _collect_page_images(page, page_num: int, page_area: float, start_image_num: int) -> tuple[list[ImageInfo], int]:
    """Extraire les images de la page (bbox affichée + dimensions intrinsèques)."""
    images: list[ImageInfo] = []
    image_num = start_image_num
    intrinsic = {info[0]: (info[2], info[3]) for info in page.get_images(full=True) if len(info) >= 4}

    for info in page.get_image_info(xrefs=True):
        bbox = info.get("bbox")
        if not bbox:
            continue
        xref = info.get("xref", 0)
        w, h = intrinsic.get(xref, (info.get("width", 0), info.get("height", 0)))
        area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
        coverage = area / page_area if page_area else 0.0
        images.append(ImageInfo(
            page_num       = page_num,
            image_num      = image_num,
            bbox           = tuple(bbox),
            width          = int(w or 0),
            height         = int(h or 0),
            coverage_ratio = coverage,
        ))
        image_num += 1
    return images, image_num


def _collect_page_tables(page, page_num: int, start_table_num: int) -> tuple[list[TableInfo], int]:
    """Extraire les tableaux vectoriels (fitz find_tables, ≥ 1.23)."""
    tables: list[TableInfo] = []
    table_num = start_table_num
    try:
        finder = page.find_tables()
        found = list(finder.tables)
    except Exception:
        return tables, table_num

    for t in found:
        try:
            rows = int(getattr(t, "row_count", 0) or len(t.extract() or []))
        except Exception:
            rows = 0
        try:
            cols = int(getattr(t, "col_count", 0) or 0)
        except Exception:
            cols = 0
        tables.append(TableInfo(
            page_num  = page_num,
            table_num = table_num,
            bbox      = tuple(getattr(t, "bbox", (0, 0, 0, 0))),
            n_rows    = rows,
            n_cols    = cols,
        ))
        table_num += 1
    return tables, table_num


def inspect_pdf(pdf_path) -> PDFInspection:
    """
    Ouvrir un PDF UNE fois et collecter tous les faits structurels.

    Aucune décision métier ici — voir `classify_inspection`.
    """
    path = Path(pdf_path)
    pdf_hash = _sha256(path)
    file_size = path.stat().st_size

    pages:  list[PageInfo]  = []
    lines:  list[LineInfo]  = []
    images: list[ImageInfo] = []
    tables: list[TableInfo] = []

    line_num = image_num = table_num = 0

    with fitz.open(str(path)) as doc:
        n_pages      = doc.page_count
        docinfo      = dict(doc.metadata or {})
        try:
            xmp_xml = doc.get_xml_metadata() or ""
        except Exception:
            xmp_xml = ""
        pdf_version  = _read_pdf_version(doc)
        is_encrypted = bool(getattr(doc, "is_encrypted", False))
        is_form_pdf  = bool(getattr(doc, "is_form_pdf", False))

        for page in doc:
            page_num   = page.number
            page_area  = page.rect.width * page.rect.height or 1.0
            fonts      = page.get_fonts()
            n_fonts    = len(fonts)
            drawings_n = len(page.get_drawings())
            img_infos  = page.get_image_info(xrefs=True)
            max_cov    = _max_image_coverage(img_infos, page_area)

            page_lines, native_chars, ocr_chars = _collect_page_lines(page, page_num, line_num)
            line_num += len(page_lines)
            lines.extend(page_lines)

            page_images, image_num = _collect_page_images(page, page_num, page_area, image_num)
            images.extend(page_images)

            page_tables, table_num = _collect_page_tables(page, page_num, table_num)
            tables.extend(page_tables)

            char_count = native_chars + ocr_chars
            pages.append(PageInfo(
                page_num             = page_num,
                n_lines              = len(page_lines),
                n_images             = len(page_images),
                n_fonts              = n_fonts,
                n_tables             = len(page_tables),
                char_count           = char_count,
                native_char_count    = native_chars,
                ocr_char_count       = ocr_chars,
                drawing_count        = drawings_n,
                image_coverage_ratio = round(max_cov, 4),
                page_width           = float(page.rect.width),
                page_height          = float(page.rect.height),
                rotation             = int(page.rotation or 0),
                has_text             = char_count > 0,
                has_native_text      = native_chars > 0,
                has_ocr_layer        = ocr_chars > 0,
                has_image            = len(page_images) > 0,
                has_full_page_image  = max_cov >= _FULL_PAGE_THRESHOLD,
                has_vector_table     = len(page_tables) > 0,
                has_vector_graphics  = drawings_n > 0,
            ))

    # Metadata source (decision)
    xmp        = parse_xmp(xmp_xml)
    metadata   = {"docinfo": docinfo, "xmp": xmp}
    normalized = normalize_metadata(metadata)
    scores     = _category_score(normalized)
    src_cat, src_conf, src_sigs = _decide_source_category(scores, normalized)
    src_tool   = _detect_tool(normalized["creator"]) or _detect_tool(normalized["producer"]) or "Unknown"

    return PDFInspection(
        pdf_hash             = pdf_hash,
        file_size            = file_size,
        n_pages              = n_pages,
        pdf_version          = pdf_version,
        is_encrypted         = is_encrypted,
        is_form_pdf          = is_form_pdf,
        metadata_raw         = docinfo,
        metadata_normalized  = normalized,
        metadata_xmp         = xmp,
        source_category      = src_cat,
        source_tool          = src_tool,
        source_confidence    = round(src_conf, 2),
        source_signals       = src_sigs,
        pages                = pages,
        lines                = lines,
        images               = images,
        tables               = tables,
        extracted_at         = datetime.now(),
        fitz_version         = fitz.__version__,
    )


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 6. CLASSIFIER — page_type, extraction_strategy, score qualité OCR          ║
# ╚════════════════════════════════════════════════════════════════════════════╝

_REPLACEMENT_CHARS = {"�"}


def _text_quality_score(text: str) -> float:
    """
    Score 0–1 sur la qualité d'une chaîne issue d'OCR.
      - pénalité forte sur les caractères de remplacement Unicode (�)
      - pénalité sur les chars de contrôle
      - bonus si la longueur moyenne des mots est plausible (3–10)
    """
    if not text:
        return 0.0
    n = len(text)
    n_repl = sum(1 for c in text if c in _REPLACEMENT_CHARS)
    n_ctrl = sum(1 for c in text if ord(c) < 32 and c not in "\n\r\t")
    bad_ratio = (n_repl + n_ctrl) / n
    score = max(0.0, 1.0 - 4.0 * bad_ratio)

    words = [w for w in text.split() if w]
    if words:
        avg_len = sum(len(w) for w in words) / len(words)
        if 3.0 <= avg_len <= 10.0:
            score = min(1.0, score + 0.10)
        elif avg_len < 2.0 or avg_len > 15.0:
            score = max(0.0, score - 0.20)
    return round(score, 3)


def _decide_page_type(p: PageInfo) -> str:
    """
    Règles ordonnées (la première qui matche gagne) :

      1. Page vide                                              → empty
      2. Aucune font + image pleine page                        → scanned
      3. Image pleine page + couche OCR (texte invisible)       → scanned_ocr_*
      4. Image pleine page + texte natif                        → mixed
      5. Image pleine page sans texte natif décisif             → scanned
      6. Fonts + texte natif (+ image)                          → native_with_image
      7. Fonts + texte natif                                    → native
      8. Fallback                                               → unknown
    """
    if p.char_count < 10 and p.n_images == 0 and p.drawing_count < 3:
        return PAGE_TYPE_EMPTY
    if p.n_fonts == 0 and p.has_full_page_image:
        return PAGE_TYPE_SCANNED
    if p.has_full_page_image and p.has_ocr_layer and p.ocr_char_count >= _MIN_OCR_CHARS:
        if (p.text_quality_score or 0.0) >= _OCR_QUALITY_THRESHOLD:
            return PAGE_TYPE_SCANNED_OCR_GOOD
        return PAGE_TYPE_SCANNED_OCR_BAD
    if p.has_full_page_image and p.has_native_text and p.native_char_count >= _MIN_NATIVE_CHARS:
        return PAGE_TYPE_MIXED
    if p.has_full_page_image:
        return PAGE_TYPE_SCANNED
    if p.n_fonts > 0 and p.native_char_count >= _MIN_NATIVE_CHARS:
        return PAGE_TYPE_NATIVE_WITH_IMAGE if p.has_image else PAGE_TYPE_NATIVE
    return PAGE_TYPE_UNKNOWN


def _decide_strategy(page_type: str) -> str:
    if page_type in (PAGE_TYPE_NATIVE, PAGE_TYPE_NATIVE_WITH_IMAGE, PAGE_TYPE_SCANNED_OCR_GOOD):
        return STRATEGY_NATIVE
    if page_type in (PAGE_TYPE_SCANNED, PAGE_TYPE_SCANNED_OCR_BAD):
        return STRATEGY_OCR
    if page_type == PAGE_TYPE_MIXED:
        return STRATEGY_HYBRID
    if page_type == PAGE_TYPE_EMPTY:
        return STRATEGY_SKIP
    return STRATEGY_HYBRID


def _ocr_text_for_page(insp: PDFInspection, page_num: int) -> str:
    return " ".join(l.text for l in insp.lines if l.page_num == page_num and l.is_invisible)


def classify_inspection(insp: PDFInspection) -> PDFInspection:
    """
    Mute chaque PageInfo : page_type, extraction_strategy, text_quality_score, tool.
    Retourne le même objet (mutation in-place).
    """
    for p in insp.pages:
        if p.has_ocr_layer and p.has_full_page_image:
            p.text_quality_score = _text_quality_score(_ocr_text_for_page(insp, p.page_num))

    for p in insp.pages:
        p.page_type           = _decide_page_type(p)
        p.extraction_strategy = _decide_strategy(p.page_type)

    for p in insp.pages:
        p.tool = _detect_page_tool(p.page_type, insp.source_category, insp.metadata_normalized)

    return insp


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 7. SYNTHÈSE — doc_summary                                                  ║
# ╚════════════════════════════════════════════════════════════════════════════╝

def _content_type(insp: PDFInspection) -> str:
    types = [p.page_type for p in insp.pages]
    if not types:
        return "empty"
    n = len(types)
    n_scanned_no_ocr = sum(t == PAGE_TYPE_SCANNED for t in types)
    n_scanned_ocr    = sum(t in (PAGE_TYPE_SCANNED_OCR_GOOD, PAGE_TYPE_SCANNED_OCR_BAD) for t in types)
    n_native         = sum(t in (PAGE_TYPE_NATIVE, PAGE_TYPE_NATIVE_WITH_IMAGE) for t in types)
    n_empty          = sum(t == PAGE_TYPE_EMPTY for t in types)

    if n_empty == n:
        return "empty"
    n_useful = n - n_empty
    if n_scanned_no_ocr / n_useful >= _DOC_AGGREGATION_RATIO:
        return "scanned_no_text"
    if (n_scanned_ocr + n_scanned_no_ocr) / n_useful >= _DOC_AGGREGATION_RATIO:
        return "scanned_with_ocr" if n_scanned_ocr > 0 else "scanned_no_text"
    if n_native / n_useful >= _DOC_AGGREGATION_RATIO:
        return "native"
    return "mixed"


def _ocr_quality_label(insp: PDFInspection) -> str:
    scores = [p.text_quality_score for p in insp.pages if p.text_quality_score is not None]
    if not scores:
        return "not_applicable"
    avg = sum(scores) / len(scores)
    if avg >= 0.85: return "good"
    if avg >= 0.60: return "degraded"
    return "unreliable"


def _recommended_strategy(insp: PDFInspection, content_type: str) -> str:
    if content_type == "native":
        return "use_native_extraction"
    if content_type == "scanned_no_text":
        return "run_ocr"
    if content_type == "scanned_with_ocr":
        return "use_existing_ocr" if _ocr_quality_label(insp) == "good" else "rerun_ocr"
    if content_type == "mixed":
        return "per_page_routing"
    return "skip"


def _tools_per_page_type(insp: PDFInspection) -> dict:
    out: dict[str, dict[str, int]] = {}
    for p in insp.pages:
        out.setdefault(p.page_type, {}).setdefault(p.tool, 0)
        out[p.page_type][p.tool] += 1
    return out


def build_doc_summary(insp: PDFInspection) -> dict:
    """JSON de synthèse au niveau document, directement consommable en aval."""
    page_type_counts = dict(Counter(p.page_type for p in insp.pages))
    n_useful = max(1, sum(c for t, c in page_type_counts.items() if t != PAGE_TYPE_EMPTY))

    n_scanned = sum(c for t, c in page_type_counts.items()
                    if t in (PAGE_TYPE_SCANNED, PAGE_TYPE_SCANNED_OCR_GOOD, PAGE_TYPE_SCANNED_OCR_BAD))
    n_native  = sum(c for t, c in page_type_counts.items()
                    if t in (PAGE_TYPE_NATIVE, PAGE_TYPE_NATIVE_WITH_IMAGE))

    content = _content_type(insp)
    ocr_quality = _ocr_quality_label(insp)
    quality_scores = [p.text_quality_score for p in insp.pages if p.text_quality_score is not None]
    avg_quality = round(sum(quality_scores) / len(quality_scores), 3) if quality_scores else None

    pages_needing_ocr = [
        p.page_num for p in insp.pages
        if p.extraction_strategy == STRATEGY_OCR and p.page_type != PAGE_TYPE_SCANNED_OCR_BAD
    ]
    pages_needing_reocr = [
        p.page_num for p in insp.pages if p.page_type == PAGE_TYPE_SCANNED_OCR_BAD
    ]

    return {
        "pdf_hash":              insp.pdf_hash,
        "file_size_bytes":       insp.file_size,
        "n_pages":               insp.n_pages,
        "source_category":       insp.source_category,
        "source_tool":           insp.source_tool,
        "source_confidence":     insp.source_confidence,
        "source_signals":        insp.source_signals,
        "creator_raw":           insp.metadata_raw.get("creator"),
        "producer_raw":          insp.metadata_raw.get("producer"),
        "pdf_version":           insp.pdf_version,
        "creation_date":         insp.metadata_raw.get("creationDate"),
        "modification_date":     insp.metadata_raw.get("modDate"),
        "content_type":          content,
        "is_scanned":            content in ("scanned_no_text", "scanned_with_ocr"),
        "has_text_layer":        any(p.has_text for p in insp.pages),
        "ocr_quality":           ocr_quality,
        "ocr_quality_score":     avg_quality,
        "page_type_counts":      page_type_counts,
        "scanned_page_ratio":    round(n_scanned / n_useful, 3),
        "native_page_ratio":     round(n_native  / n_useful, 3),
        "is_encrypted":          insp.is_encrypted,
        "has_form_fields":       insp.is_form_pdf,
        "n_vector_tables":       sum(p.n_tables for p in insp.pages),
        "n_images_total":        sum(p.n_images for p in insp.pages),
        "recommended_strategy":  _recommended_strategy(insp, content),
        "pages_needing_ocr":     pages_needing_ocr,
        "pages_needing_reocr":   pages_needing_reocr,
        "tools_per_page_type":   _tools_per_page_type(insp),
        "analyzed_at":           insp.extracted_at.isoformat() if insp.extracted_at else None,
        "fitz_version":          insp.fitz_version,
        "inspector_version":     insp.inspector_version,
    }


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 8. PIPELINE — point d'entrée public                                        ║
# ╚════════════════════════════════════════════════════════════════════════════╝

def inspection_to_dataframes(insp: PDFInspection) -> dict:
    """Convertir un PDFInspection en {line_df, image_df, page_df}."""
    line_df  = pd.DataFrame([asdict(l) for l in insp.lines])
    image_df = pd.DataFrame([asdict(i) for i in insp.images])
    page_df  = pd.DataFrame([asdict(p) for p in insp.pages])

    for df in (line_df, image_df, page_df):
        if not df.empty:
            df.insert(0, "pdf_hash", insp.pdf_hash)
    return {"line_df": line_df, "image_df": image_df, "page_df": page_df}


def parse_pdf(pdf_path) -> dict:
    """
    Inspecter, classifier et matérialiser un PDF en 1 appel, 1 ouverture fitz.

    Sortie :
      {
        "line_df":     DataFrame,  # 1 ligne = 1 ligne de texte
        "image_df":    DataFrame,  # 1 ligne = 1 image
        "page_df":     DataFrame,  # 1 ligne = 1 page (page_type + flags)
        "doc_summary": dict,       # synthèse niveau document
      }
    """
    insp = inspect_pdf(pdf_path)
    insp = classify_inspection(insp)
    return {
        **inspection_to_dataframes(insp),
        "doc_summary": build_doc_summary(insp),
    }


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 9. RECONSTRUCTION — apply_changes (pattern symétrique à parse_word)        ║
# ╚════════════════════════════════════════════════════════════════════════════╝

def _hex_to_rgb_float(hex_color: str) -> tuple[float, float, float]:
    """'#RRGGBB' → (r, g, b) floats dans [0, 1]. Défaut noir."""
    s = (hex_color or "").lstrip("#")
    if len(s) != 6:
        return (0.0, 0.0, 0.0)
    try:
        return (int(s[0:2], 16) / 255.0,
                int(s[2:4], 16) / 255.0,
                int(s[4:6], 16) / 255.0)
    except ValueError:
        return (0.0, 0.0, 0.0)


def _select_pdf_font(bold: bool, italic: bool) -> str:
    """
    Sélection d'une police « standard 14 » PyMuPDF selon le style.

    Limitation PyMuPDF : seules les Standard 14 fonts (Helvetica, Times,
    Courier + variantes) sont disponibles sans embedding. Les polices
    custom du PDF original ne peuvent pas être réutilisées telles quelles
    via insert_textbox sans embedder le fichier .ttf manuellement.
    """
    if bold and italic:
        return "Helvetica-BoldOblique"
    if bold:
        return "Helvetica-Bold"
    if italic:
        return "Helvetica-Oblique"
    return "Helvetica"


def apply_changes(
    pdf_in,
    span_changes: dict,
    pdf_out,
    *,
    keep_images: bool = True,
) -> dict:
    """
    Reconstruit un PDF en remplaçant le texte de certains spans, en préservant
    les positions, tailles, couleurs et le gras/italique.

    Pattern symétrique à `parse_word.apply_changes` :

        extract  : parse_pdf(pdf_in)                 → line_df avec span_id
        modify   : on construit {span_id: nouveau_texte}
        rebuild  : apply_changes(pdf_in, span_changes, pdf_out)

    Args:
        pdf_in        : chemin du PDF source
        span_changes  : dict {span_id: nouveau_texte} ; les span_id non listés
                        gardent leur texte original.
                        Format span_id : "p_<page>_<line>" (cf. LineInfo).
        pdf_out       : chemin du PDF de sortie
        keep_images   : conserver les images embarquées (défaut True)

    Returns:
        dict {output_path, spans_replaced, spans_skipped, warnings}

    Limitations :
        - Polices : limité aux Standard 14 PyMuPDF (Helvetica/Times/Courier).
          Les polices originales custom ne sont pas réembed-ables ici sans
          fournir le .ttf, donc le rendu peut différer visuellement.
        - Bbox : si le texte traduit est plus long que l'original, on essaie
          de réduire la taille de police progressivement (90, 80, 70, 60 %).
    """
    pdf_in  = Path(pdf_in)
    pdf_out = Path(pdf_out)

    # On a besoin du line_df pour récupérer bbox, color, font_size, bold/italic
    # par span_id. On ne ré-extrait que ce qui est nécessaire.
    insp = inspect_pdf(pdf_in)
    by_span_id = {l.span_id: l for l in insp.lines}

    warnings: list[str] = []
    replaced = 0
    skipped  = 0

    doc = fitz.open(str(pdf_in))
    try:
        for span_id, new_text in span_changes.items():
            line = by_span_id.get(span_id)
            if line is None:
                warnings.append(f"span_id {span_id!r} introuvable — skip")
                skipped += 1
                continue
            page_idx = line.page_num
            if page_idx < 0 or page_idx >= len(doc):
                warnings.append(f"span_id {span_id!r} : page {page_idx} hors limites")
                skipped += 1
                continue
            page = doc[page_idx]
            bbox = fitz.Rect(*line.bbox)

            # 1. Effacer le texte natif via redaction (rectangle blanc)
            page.add_redact_annot(bbox, fill=(1, 1, 1))
            page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_NONE if keep_images
                       else fitz.PDF_REDACT_IMAGE_REMOVE
            )

            # 2. Réinscrire le texte modifié dans la même bbox, mêmes attributs
            font_name = _select_pdf_font(line.bold, line.italic)
            r, g, b   = _hex_to_rgb_float(line.color or "#000000")
            size      = line.font_size or 11.0

            try:
                rc = page.insert_textbox(
                    bbox, new_text,
                    fontname=font_name, fontsize=size, color=(r, g, b),
                    align=fitz.TEXT_ALIGN_LEFT,
                )
                if rc < 0:
                    # Texte plus long : on rétrécit progressivement
                    fitted = False
                    for shrink in (0.90, 0.80, 0.70, 0.60):
                        rc2 = page.insert_textbox(
                            bbox, new_text,
                            fontname=font_name, fontsize=size * shrink, color=(r, g, b),
                            align=fitz.TEXT_ALIGN_LEFT,
                        )
                        if rc2 >= 0:
                            fitted = True
                            break
                    if not fitted:
                        warnings.append(f"span_id {span_id!r} : texte trop long pour la bbox même réduit")
                replaced += 1
            except Exception as e:
                warnings.append(f"span_id {span_id!r} : insertion échouée — {e}")
                skipped += 1

        doc.save(str(pdf_out))
    finally:
        doc.close()

    return {
        "output_path":    pdf_out,
        "spans_replaced": replaced,
        "spans_skipped":  skipped,
        "warnings":       warnings,
    }


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║ 10. CLI minimal                                                            ║
# ╚════════════════════════════════════════════════════════════════════════════╝

if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 2:
        print("Usage: python parse_pdf.py <pdf_path>", file=sys.stderr)
        sys.exit(1)

    result = parse_pdf(sys.argv[1])
    print(json.dumps(result["doc_summary"], indent=2, ensure_ascii=False, default=str))

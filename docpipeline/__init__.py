"""
docpipeline — Pipeline modulaire de traitement documentaire IA.

Architecture: 4 briques × N format pipelines.
  - parsing    : extraction → DataFrame standardisé
  - retrieval  : filtrage progressif (Python ou SQL)
  - generation : LLM unifié (résumé, traduction, QA)
  - conversion : PDF → Word (Smart/Text/OCR + Enhancer)
  - translation: traduction Word/PDF avec préservation des styles
  - excel_agent: agent SQL en langage naturel

API simplifiée — usage en deux lignes :

    from docpipeline import convert, parse, classify, summarize

    # Conversion d'un format vers un autre
    convert("contrat.pdf", "contrat.docx")          # PDF → Word
    convert("rapport.pdf", "tableaux.xlsx")         # PDF → Excel
    convert("memo.docx",   "memo.pdf")              # Word → PDF

    # Parsing universel (détection automatique du format)
    result = parse("document.pdf")                  # ou .docx, .xlsx, .pptx, .eml

    # Classification
    info = classify("document.pdf")

    # Résumé (LLM)
    summary = summarize("rapport.pdf")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

__version__ = "0.4.0"

# Re-export des briques principales pour usage direct
from .parsing.pdf import classify_pdf as _classify_pdf
from .parsing.pdf import extract_text_dataframe, extract_full_with_style
from .parsing.pdf.tables import pdf_to_excel as _pdf_to_excel
from .parsing.word import parse_word as _parse_word
from .parsing.excel import ingest_excel as _ingest_excel
from .conversion import convert_pdf_to_word, ConversionResult


# ── API simplifiée — top-level ────────────────────────────────────────────────

def convert(
    input_path:  str | Path,
    output_path: str | Path,
    **options: Any,
) -> Path:
    """
    Convertir un document d'un format à un autre, en préservant le contenu original.

    Conversions supportées :
        PDF  → DOCX   (sélection auto du moteur : text/smart/ocr)
        PDF  → XLSX   (extraction des tableaux)
        DOCX → PDF    (via fitz/Word)

    Args:
        input_path  : chemin du fichier source
        output_path : chemin du fichier cible (extension détermine la conversion)
        **options   : options spécifiques (force_engine, enhance, ocr_lang, etc.)

    Returns:
        Path du fichier généré

    Examples:
        convert("contrat.pdf", "contrat.docx")
        convert("rapport.pdf", "tableaux.xlsx")
        convert("memo.docx",   "memo.pdf")
    """
    input_path  = Path(input_path)
    output_path = Path(output_path)

    src_ext = input_path.suffix.lower()
    dst_ext = output_path.suffix.lower()

    if not input_path.exists():
        raise FileNotFoundError(f"Fichier source introuvable : {input_path}")

    # PDF → DOCX
    if src_ext == ".pdf" and dst_ext == ".docx":
        result = convert_pdf_to_word(input_path, output_path, **options)
        return result.output_path

    # PDF → XLSX (tableaux)
    if src_ext == ".pdf" and dst_ext == ".xlsx":
        return _pdf_to_excel(input_path, output_path)

    # DOCX → PDF
    if src_ext == ".docx" and dst_ext == ".pdf":
        return _docx_to_pdf(input_path, output_path)

    # XLSX → SQLite (base requêtable)
    if src_ext == ".xlsx" and dst_ext in (".db", ".sqlite"):
        return _ingest_excel(input_path, output_path, output_format="sqlite")

    raise ValueError(
        f"Conversion non supportée : {src_ext} → {dst_ext}. "
        f"Combinaisons disponibles : pdf→docx, pdf→xlsx, docx→pdf, xlsx→db"
    )


def parse(input_path: str | Path) -> Any:
    """
    Parser un document, format détecté automatiquement.

    Returns un objet adapté au format :
        .pdf  → DataFrame texte
        .docx → WordParseResult (df + toc + spans + tables)
        .xlsx → Path vers SQLite généré
        .pptx → PPTXParseResult
        .eml  → EmailParseResult
    """
    input_path = Path(input_path)
    ext        = input_path.suffix.lower()

    if ext == ".pdf":
        return extract_text_dataframe(input_path)
    if ext == ".docx":
        return _parse_word(input_path)
    if ext == ".xlsx":
        from .parsing.excel import ingest_excel
        return ingest_excel(input_path, output_format="sqlite")
    if ext == ".pptx":
        from .parsing.pptx import parse_pptx
        return parse_pptx(input_path)
    if ext == ".eml":
        from .parsing.email import parse_email
        return parse_email(input_path)

    raise ValueError(f"Format non supporté : {ext} (attendu : pdf/docx/xlsx/pptx/eml)")


def classify(pdf_path: str | Path):
    """Classifier un PDF (word_native / design_tool / scanned / other)."""
    return _classify_pdf(pdf_path)


def summarize(input_path: str | Path, **llm_options: Any) -> str:
    """
    Résumer un document (utilise un LLM — nécessite OPENAI_API_KEY).

    Args:
        input_path    : .pdf ou .docx
        **llm_options : passés à LLMConfig (model, temperature, etc.)
    """
    from .generation import LLMConfig, summarize_document

    parsed = parse(input_path)
    if hasattr(parsed, "df"):
        df = parsed.df
    else:
        df = parsed

    config = LLMConfig.openai(**llm_options) if llm_options else None
    return summarize_document(df, config=config).content


# ── Helpers internes ─────────────────────────────────────────────────────────

def _docx_to_pdf(docx_path: Path, pdf_path: Path) -> Path:
    """Conversion DOCX → PDF via docx2pdf si disponible, sinon LibreOffice."""
    try:
        from docx2pdf import convert as docx2pdf_convert
        docx2pdf_convert(str(docx_path), str(pdf_path))
        return pdf_path
    except ImportError:
        pass

    # Fallback : commande libreoffice (cross-platform)
    import shutil
    import subprocess
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise RuntimeError(
            "Conversion DOCX → PDF nécessite docx2pdf "
            "(pip install docx2pdf) ou LibreOffice installé."
        )
    subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf",
         "--outdir", str(pdf_path.parent), str(docx_path)],
        check=True, capture_output=True,
    )
    generated = pdf_path.parent / f"{docx_path.stem}.pdf"
    if generated != pdf_path and generated.exists():
        generated.rename(pdf_path)
    return pdf_path


__all__ = [
    "__version__",
    "convert", "parse", "classify", "summarize",
    "ConversionResult",
]

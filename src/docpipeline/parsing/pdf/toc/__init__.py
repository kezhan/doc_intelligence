"""Sous-package TOC — détection et extraction de tables des matières dans les PDF.

Trois stratégies d'extraction (ZERO LLM) :
  - native    : signets/bookmarks embarqués dans le PDF (get_toc via PyMuPDF)
  - links     : hyperliens internes utilisés comme table des matières cliquable
  - textual   : analyse du texte (lignes pointillées, titraille, leaders multilignes)

Point d'entrée principal : `detect_toc` retourne un score de confiance heuristique
et les numéros de pages où une TOC a été détectée.

Exemple d'usage :
    from docpipeline.parsing.pdf.toc import detect_toc, extract_native_toc

    result = detect_toc("contrat.pdf")
    if result.has_toc:
        toc_df = extract_native_toc("contrat.pdf")
"""

from .bookmarks import add_dataframe_toc_to_pdf
from .detector import detect_toc
from .exceptions import EmptyPDFError, InvalidPDFError, PDFReadError
from .gpt import extract_raw_toc_text, extract_toc_with_gpt, find_toc_pages
from .links import extract_toc_by_numbering, extract_toc_from_links
from .models import PageAnalysis, TocDetectionResult
from .native import (
    clean_toc_df,
    export_toc_to_excel,
    export_toc_to_json,
    extract_native_toc,
    extract_native_toc_detailed,
    filter_pdfs_with_native_toc,
    get_pdf_page_count,
    has_native_toc,
    nest_toc,
)
from .patterns import (
    TOC_KEYWORDS,
    calculate_short_line_density,
    find_dotted_leader_lines,
    find_hierarchical_structure,
    find_lines_ending_with_number,
    has_toc_keyword,
)
from .reader import extract_text_from_first_pages
from .scoring import score_page
from .textual import (
    extract_title_candidates,
    extract_toc_dotted,
    extract_toc_multiline,
    group_numbered_titles,
)

__all__ = [
    # Détection heuristique (TODO-TOC-001)
    "detect_toc",
    "TocDetectionResult",
    "PageAnalysis",
    "PDFReadError",
    "InvalidPDFError",
    "EmptyPDFError",
    "extract_text_from_first_pages",
    "score_page",
    "TOC_KEYWORDS",
    "has_toc_keyword",
    "find_dotted_leader_lines",
    "find_lines_ending_with_number",
    "find_hierarchical_structure",
    "calculate_short_line_density",
    # Extraction native — signets (TODO-TOC-002)
    "has_native_toc",
    "extract_native_toc",
    "extract_native_toc_detailed",
    "clean_toc_df",
    "nest_toc",
    "export_toc_to_json",
    "export_toc_to_excel",
    "get_pdf_page_count",
    "filter_pdfs_with_native_toc",
    # Extraction textuelle (TODO-TOC-003)
    "extract_toc_dotted",
    "extract_toc_multiline",
    "extract_title_candidates",
    "group_numbered_titles",
    # Extraction par liens (TODO-TOC-004)
    "extract_toc_from_links",
    "extract_toc_by_numbering",
    # Extraction par LLM — OpenAI (TODO-TOC-005)
    "extract_toc_with_gpt",
    "find_toc_pages",
    "extract_raw_toc_text",
    # Écriture de bookmarks
    "add_dataframe_toc_to_pdf",
]

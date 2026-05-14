"""PDF text extraction used by TOC detection."""

from __future__ import annotations

import re
from pathlib import Path

import fitz
import pdfplumber

from .exceptions import EmptyPDFError, InvalidPDFError, PDFReadError

DEFAULT_MAX_PAGES: int = 5
_NORMALIZE_SPACES_RE = re.compile(r"\s+")
_NORMALIZE_PUNCT_RE = re.compile(r"[^\w\s]+", re.UNICODE)


def normalize_text(text: str) -> str:
    """Normalise PDF text for robust matching across extractors."""
    normalised = str(text).casefold().replace("\xa0", " ")
    normalised = _NORMALIZE_PUNCT_RE.sub(" ", normalised)
    return _NORMALIZE_SPACES_RE.sub(" ", normalised).strip()


def extract_text_from_first_pages(
    pdf_path: str | Path,
    max_pages: int | None = None,
) -> list[dict[str, int | str]]:
    """Extract page text and link density signals from a PDF.

    Args:
        pdf_path: Path to the input PDF file.
        max_pages: Maximum number of first pages to inspect. If ``None``,
            inspect the full document.

    Returns:
        List of page dictionaries with one-based ``page_number``, extracted
        ``text``, and internal ``link_count`` (PyMuPDF links with ``kind == 1``).

    Raises:
        PDFReadError: If path does not exist or is not a file.
        InvalidPDFError: If the PDF cannot be opened.
        EmptyPDFError: If the PDF has no pages.
    """
    path = Path(pdf_path)

    if not path.exists():
        raise PDFReadError(f"File not found: {path}")
    if not path.is_file():
        raise PDFReadError(f"Path is not a file: {path}")

    try:
        pdf = pdfplumber.open(path)
    except Exception as exc:
        raise InvalidPDFError(f"Cannot open PDF '{path}': {exc}") from exc

    link_count_by_page: dict[int, int] = {}
    try:
        with fitz.open(path) as doc:
            for page_index, page in enumerate(doc, start=1):
                try:
                    links = page.get_links() or []
                    link_count_by_page[page_index] = sum(
                        1
                        for link in links
                        if int(link.get("kind", -1)) == 1
                    )
                except Exception:
                    link_count_by_page[page_index] = 0
    except Exception:
        # Link signal is optional; keep text extraction resilient.
        link_count_by_page = {}

    with pdf:
        if not pdf.pages:
            raise EmptyPDFError(f"PDF has no pages: {path}")

        result: list[dict[str, int | str]] = []
        pages = pdf.pages if max_pages is None else pdf.pages[:max_pages]
        for page in pages:
            try:
                raw_text = page.extract_text() or ""
            except Exception:
                raw_text = ""

            result.append(
                {
                    "page_number": page.page_number,
                    "text": raw_text,
                    "link_count": link_count_by_page.get(page.page_number, 0),
                }
            )

    return result

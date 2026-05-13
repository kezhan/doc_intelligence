"""PDF text extraction used by TOC detection."""

from __future__ import annotations

import re
from pathlib import Path

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
    """Extract text from the first ``max_pages`` pages of a PDF.

    If ``max_pages`` is ``None``, the full document is inspected.
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

            result.append({"page_number": page.page_number, "text": raw_text})

    return result

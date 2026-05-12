"""PDF text extraction used by TOC detection."""

from __future__ import annotations

from pathlib import Path

import pdfplumber

from .exceptions import EmptyPDFError, InvalidPDFError, PDFReadError

DEFAULT_MAX_PAGES: int = 5


def extract_text_from_first_pages(
    pdf_path: str | Path,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> list[dict[str, int | str]]:
    """Extract text from the first ``max_pages`` pages of a PDF."""
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
        for page in pdf.pages[:max_pages]:
            try:
                raw_text = page.extract_text() or ""
            except Exception:
                raw_text = ""

            result.append({"page_number": page.page_number, "text": raw_text})

    return result

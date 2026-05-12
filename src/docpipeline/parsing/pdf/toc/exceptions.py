"""Exceptions raised by the PDF TOC detection layer."""


class PDFReadError(Exception):
    """Raised when a PDF file cannot be read."""


class InvalidPDFError(Exception):
    """Raised when the file exists but is not a valid PDF."""


class EmptyPDFError(Exception):
    """Raised when the PDF contains no pages."""

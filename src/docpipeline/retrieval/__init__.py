"""Retrieval brick — Python (keyword/regex/embeddings) ou SQL (FTS5)."""

from .retriever import retrieve
from .sql_backend import SQLRetriever

__all__ = ["retrieve", "SQLRetriever"]

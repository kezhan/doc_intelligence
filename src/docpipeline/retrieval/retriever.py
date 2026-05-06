"""
TODO-023 — Retrieval: progressive DataFrame filtering.

Current strategy: keyword → regex → (optional) embeddings
Target evolution: SQL on structured store.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd


def retrieve(
    df: pd.DataFrame,
    query: str,
    *,
    top_k: int = 20,
    use_embeddings: bool = False,
    embedding_model: Any = None,
) -> pd.DataFrame:
    """
    TODO-023 — Filter a parsed document DataFrame for the most relevant rows.

    Input : DataFrame with a 'text' column + user query string
    Output: filtered sub-DataFrame (at most top_k rows), sorted by relevance

    Strategy (progressive narrowing):
      1. Keyword filter  — keep rows containing any query word
      2. Regex scoring   — boost rows matching the full phrase
      3. Embedding rerank (optional) — cosine similarity reranking
    """
    if "text" not in df.columns:
        raise ValueError("DataFrame must have a 'text' column")

    tokens = _tokenize(query)
    working = df.copy()

    # 1. Keyword filter
    if tokens:
        pattern = "|".join(re.escape(t) for t in tokens)
        mask = working["text"].str.contains(pattern, case=False, na=False, regex=True)
        working = working[mask]

    if working.empty:
        return working.head(top_k)

    # 2. Relevance scoring via token overlap
    working = working.copy()
    working["_score"] = working["text"].apply(lambda t: _keyword_score(t, tokens))

    if use_embeddings and embedding_model is not None:
        working = _rerank_with_embeddings(working, query, embedding_model)
    else:
        working = working.sort_values("_score", ascending=False)

    result = working.head(top_k).drop(columns=["_score"])
    return result.reset_index(drop=True)


# ── helpers ───────────────────────────────────────────────────────────────────

def _tokenize(query: str) -> list[str]:
    return [w.lower() for w in re.findall(r"\w+", query) if len(w) > 2]


def _keyword_score(text: str, tokens: list[str]) -> float:
    text_lower = text.lower()
    return sum(1 for t in tokens if t in text_lower) / max(len(tokens), 1)


def _rerank_with_embeddings(
    df: pd.DataFrame,
    query: str,
    model: Any,
) -> pd.DataFrame:
    """
    Rerank using cosine similarity between query embedding and row embeddings.
    `model` must expose an `encode(texts: list[str]) -> np.ndarray` interface
    (compatible with sentence-transformers).
    """
    texts = df["text"].tolist()
    query_vec = model.encode([query])[0]
    doc_vecs = model.encode(texts)

    similarities = np.array([_cosine(query_vec, v) for v in doc_vecs])
    df = df.copy()
    df["_score"] = similarities
    return df.sort_values("_score", ascending=False)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)

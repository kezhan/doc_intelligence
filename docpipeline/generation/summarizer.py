"""
TODO-022 — Document summarization pipeline built on the unified LLM client.
"""

from __future__ import annotations

import pandas as pd

from .llm_client import LLMClient, LLMConfig, LLMResponse

_SYSTEM = (
    "You are a professional document analyst. "
    "Produce concise, structured summaries in the same language as the input."
)

_CHUNK_SIZE = 3000  # characters per chunk to stay within context limits


def summarize_document(
    df: pd.DataFrame,
    *,
    config: LLMConfig | None = None,
    language_hint: str = "",
) -> LLMResponse:
    """
    TODO-022 — Summarize a parsed document DataFrame.

    Input : DataFrame produced by any parsing brick (must have a 'text' column)
    Output: LLMResponse whose .content is the structured summary
    """
    if "text" not in df.columns:
        raise ValueError("DataFrame must contain a 'text' column")

    client = LLMClient(config or LLMConfig.openai())
    full_text = "\n".join(df["text"].dropna().astype(str).tolist())

    chunks = _split_text(full_text, _CHUNK_SIZE)

    if len(chunks) == 1:
        return client.complete(
            "Summarise this document in a structured format with key points and conclusions.",
            context=chunks[0],
            system=_SYSTEM,
        )

    # Multi-chunk: summarize each chunk then synthesize
    partial_summaries: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        resp = client.complete(
            f"Summarise part {i}/{len(chunks)} of this document.",
            context=chunk,
            system=_SYSTEM,
        )
        partial_summaries.append(resp.content)

    combined = "\n\n---\n\n".join(partial_summaries)
    return client.complete(
        "Synthesise the following partial summaries into one final structured summary.",
        context=combined,
        system=_SYSTEM,
    )


def _split_text(text: str, chunk_size: int) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end
    return chunks

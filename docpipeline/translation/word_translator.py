"""
TODO-016 — Word document translation with style preservation.

Pipeline:
  1. Parse XML → extract spans with stable IDs   (parse_word)
  2. Build prompt with glossary context          (glossary.prompt_context)
  3. Call LLM asking it to preserve span IDs    (LLMClient)
  4. Reconstruct: remap translated spans back    (this module)
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from docx import Document
from docx.oxml.ns import qn

from ..generation.llm_client import LLMClient, LLMConfig
from ..parsing.word.parser import parse_word
from .glossary import Glossary, detect_business_terms


_SYSTEM = (
    "You are a professional translator specializing in technical and insurance documents. "
    "You will receive JSON containing text spans, each with a unique 'span_id'. "
    "Translate every 'text' value but PRESERVE the span_id keys exactly. "
    "Return valid JSON with the same structure."
)

_PROMPT_TEMPLATE = """\
Translate the following document spans from {source_lang} to {target_lang}.
Preserve all span_id keys. Only translate the 'text' values.

Glossary hints (follow strictly):
{glossary_context}

Spans (JSON):
{spans_json}

Return ONLY the translated JSON — no explanations.
"""


def translate_word(
    docx_path: str | Path,
    target_lang: str = "en",
    source_lang: str = "fr",
    *,
    glossary: Glossary | None = None,
    config: LLMConfig | None = None,
    output_path: str | Path | None = None,
    chunk_size: int = 60,
) -> Path:
    """
    TODO-016 — Translate a .docx preserving styles.

    Input : path to a .docx
    Output: path to the translated .docx (with identical formatting)
    """
    docx_path = Path(docx_path)
    output_path = Path(output_path) if output_path else docx_path.with_stem(
        f"{docx_path.stem}_{target_lang}"
    )

    parsed = parse_word(docx_path)
    spans = parsed.spans

    # Detect business terms across full text for glossary context
    full_text = " ".join(s["text"] for s in spans)
    detected_terms = detect_business_terms(full_text, glossary) if glossary else []
    glossary_ctx = glossary.prompt_context(detected_terms, target_lang) if glossary else ""

    # Translate in chunks to stay within context window
    translated_map: dict[str, str] = {}
    for chunk in _chunk_spans(spans, chunk_size):
        payload = {s["span_id"]: {"text": s["text"]} for s in chunk}
        prompt = _PROMPT_TEMPLATE.format(
            source_lang=source_lang,
            target_lang=target_lang,
            glossary_context=glossary_ctx or "(no glossary provided)",
            spans_json=json.dumps(payload, ensure_ascii=False, indent=2),
        )
        client = LLMClient(config or LLMConfig.openai())
        resp = client.complete(prompt, system=_SYSTEM)
        chunk_translations = _parse_llm_json(resp.content)
        for span_id, val in chunk_translations.items():
            if isinstance(val, dict):
                translated_map[span_id] = val.get("text", "")
            elif isinstance(val, str):
                translated_map[span_id] = val

    # Reconstruct the .docx with translated text
    _write_translated_docx(docx_path, output_path, spans, translated_map)
    return output_path


# ── reconstruction ────────────────────────────────────────────────────────────

def _write_translated_docx(
    source_path: Path,
    output_path: Path,
    spans: list[dict[str, Any]],
    translated_map: dict[str, str],
) -> None:
    """Inject translated text back into the docx XML, preserving all formatting."""
    doc = Document(str(source_path))
    span_idx = 0

    for para in doc.paragraphs:
        for run in para.runs:
            if span_idx >= len(spans):
                break
            span = spans[span_idx]
            # Match run to span by original text (spans were built in order)
            if run.text == span["text"]:
                translated = translated_map.get(span["span_id"])
                if translated:
                    run.text = translated
                span_idx += 1

    doc.save(str(output_path))


# ── helpers ───────────────────────────────────────────────────────────────────

def _chunk_spans(
    spans: list[dict[str, Any]],
    chunk_size: int,
) -> list[list[dict[str, Any]]]:
    return [spans[i:i + chunk_size] for i in range(0, len(spans), chunk_size)]


def _parse_llm_json(content: str) -> dict[str, Any]:
    """Extract JSON from LLM response, tolerating markdown code fences."""
    content = content.strip()
    # Strip ```json ... ``` fences if present
    fence = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", content)
    if fence:
        content = fence.group(1)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {}

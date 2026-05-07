"""Helper LLM partagé — singleton client + fallback gracieux sans clé API.

Toutes les fonctions LLM du chapitre passent par `call_llm()`. En l'absence
de OPENAI_API_KEY, on retourne `None` ; chaque appelant décide de son fallback.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

DEFAULT_MODEL = "gpt-4.1-mini"


@lru_cache(maxsize=1)
def _client():
    from openai import OpenAI
    return OpenAI()


def llm_available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def call_llm(prompt: str, *, model: str = DEFAULT_MODEL) -> Optional[str]:
    """Appel LLM unifié. Retourne None si OPENAI_API_KEY absent."""
    if not llm_available():
        return None
    resp = _client().responses.create(model=model, input=prompt)
    return resp.output_text.strip()

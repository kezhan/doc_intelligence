"""Generation brick — unified LLM orchestration."""

from .llm_client import LLMClient, LLMConfig, LLMResponse
from .summarizer import summarize_document

__all__ = ["LLMClient", "LLMConfig", "LLMResponse", "summarize_document"]

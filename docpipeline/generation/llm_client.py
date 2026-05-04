"""
TODO-021 — Single LLM orchestration function for the entire pipeline.

Supports OpenAI and Anthropic. Provider is selected via LLMConfig.
All pipeline code should import from here — never call provider SDKs directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


@dataclass
class LLMConfig:
    provider: LLMProvider = LLMProvider.OPENAI
    model: str = "gpt-4o-mini"
    temperature: float = 0.2
    max_tokens: int = 4096
    structured_output: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def openai(cls, model: str = "gpt-4o-mini", **kwargs: Any) -> "LLMConfig":
        return cls(provider=LLMProvider.OPENAI, model=model, **kwargs)

    @classmethod
    def anthropic(cls, model: str = "claude-sonnet-4-6", **kwargs: Any) -> "LLMConfig":
        return cls(provider=LLMProvider.ANTHROPIC, model=model, **kwargs)


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: LLMProvider
    usage: dict[str, int] = field(default_factory=dict)
    raw: Any = None


class LLMClient:
    """
    TODO-021 — Unified LLM entry point for the full pipeline.

    Usage:
        client = LLMClient(LLMConfig.openai())
        resp = client.complete("Summarise this text", context="...")
    """

    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig()

    def complete(
        self,
        prompt: str,
        *,
        context: str = "",
        system: str = "",
        config_override: LLMConfig | None = None,
    ) -> LLMResponse:
        """
        Main entry point for all LLM calls in the pipeline.

        Args:
            prompt  : user instruction
            context : document context injected into the user message
            system  : system-level instruction (override default)
            config_override: one-shot config override for this call only
        """
        cfg = config_override or self.config
        messages = _build_messages(prompt, context=context, system=system)

        if cfg.provider == LLMProvider.OPENAI:
            return self._call_openai(messages, cfg)
        elif cfg.provider == LLMProvider.ANTHROPIC:
            return self._call_anthropic(messages, cfg)
        else:
            raise ValueError(f"Unknown provider: {cfg.provider}")

    # ── provider implementations ──────────────────────────────────────────────

    def _call_openai(self, messages: list[dict[str, str]], cfg: LLMConfig) -> LLMResponse:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError("Install openai: pip install openai") from exc

        api_key = cfg.extra.get("api_key") or os.environ.get("OPENAI_API_KEY")
        client = OpenAI(api_key=api_key)

        kwargs: dict[str, Any] = {
            "model": cfg.model,
            "messages": messages,
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_tokens,
        }
        if cfg.structured_output and cfg.extra.get("response_format"):
            kwargs["response_format"] = cfg.extra["response_format"]

        resp = client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            model=resp.model,
            provider=LLMProvider.OPENAI,
            usage={
                "prompt_tokens": resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens,
            },
            raw=resp,
        )

    def _call_anthropic(self, messages: list[dict[str, str]], cfg: LLMConfig) -> LLMResponse:
        try:
            import anthropic
        except ImportError as exc:
            raise ImportError("Install anthropic: pip install anthropic") from exc

        api_key = cfg.extra.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
        client = anthropic.Anthropic(api_key=api_key)

        system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
        user_messages = [m for m in messages if m["role"] != "system"]

        resp = client.messages.create(
            model=cfg.model,
            max_tokens=cfg.max_tokens,
            system=system_msg,
            messages=user_messages,  # type: ignore[arg-type]
        )
        return LLMResponse(
            content=resp.content[0].text if resp.content else "",
            model=resp.model,
            provider=LLMProvider.ANTHROPIC,
            usage={
                "prompt_tokens": resp.usage.input_tokens,
                "completion_tokens": resp.usage.output_tokens,
            },
            raw=resp,
        )


# ── helpers ───────────────────────────────────────────────────────────────────

def _build_messages(
    prompt: str,
    *,
    context: str,
    system: str,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []

    if system:
        messages.append({"role": "system", "content": system})

    user_content = prompt
    if context:
        user_content = f"Context:\n{context}\n\n{prompt}"
    messages.append({"role": "user", "content": user_content})

    return messages

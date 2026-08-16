"""Narration providers.

`get_llm()` resolves the configured provider once per process. Resolution never
raises: a missing key, a missing SDK or an unknown provider name all degrade to
`NullProvider`, which is the deterministic grounded-only mode. Losing narration
must never take the product down.
"""
from __future__ import annotations

from functools import lru_cache

from ..config import Settings, get_settings
from .base import SYSTEM_PROMPT, LLMError, LLMProvider, NullProvider

_NULL = NullProvider()


def build_llm(settings: Settings | None = None) -> LLMProvider:
    """Construct the provider named by settings, falling back to null on any problem."""
    s = settings or get_settings()
    choice = (s.llm_provider or "none").strip().lower()

    if choice == "auto":
        # Prefer whichever key is actually present. Anthropic first only because it
        # is the provider the guardrail prompt was tuned against.
        if s.anthropic_api_key:
            choice = "anthropic"
        elif s.gemini_api_key:
            choice = "gemini"
        else:
            choice = "none"

    try:
        if choice == "anthropic":
            if not s.anthropic_api_key:
                return _NULL
            from .anthropic_provider import AnthropicProvider

            return AnthropicProvider(
                api_key=s.anthropic_api_key,
                model=s.resolved_llm_model("anthropic"),
                max_tokens=s.llm_max_tokens,
                timeout=s.llm_timeout_seconds,
            )
        if choice == "gemini":
            if not s.gemini_api_key:
                return _NULL
            from .gemini_provider import GeminiProvider

            return GeminiProvider(
                api_key=s.gemini_api_key,
                model=s.resolved_llm_model("gemini"),
                max_tokens=s.llm_max_tokens,
                timeout=s.llm_timeout_seconds,
            )
    except LLMError:
        return _NULL
    return _NULL


@lru_cache(maxsize=1)
def get_llm() -> LLMProvider:
    return build_llm()


def reset_llm_cache() -> None:
    """Used by tests and by any code that mutates settings at runtime."""
    get_llm.cache_clear()


__all__ = [
    "LLMProvider",
    "LLMError",
    "NullProvider",
    "SYSTEM_PROMPT",
    "build_llm",
    "get_llm",
    "reset_llm_cache",
]

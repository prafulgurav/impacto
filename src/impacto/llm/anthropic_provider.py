"""Claude narration via the official Anthropic SDK."""
from __future__ import annotations

from collections.abc import Iterator

from .base import LLMError

# Narration is a constrained rewrite of facts we already computed, so it does not
# need deep reasoning. Low effort keeps latency inside the SSE budget in §2.5 of
# the build brief (the `composed` event must land within 500 ms and the narration
# should not lag it by much on a 4G connection).
_EFFORT = "low"


class AnthropicProvider:
    """Wraps `anthropic` and exposes the two-method LLMProvider contract."""

    name = "anthropic"

    def __init__(self, api_key: str, model: str, max_tokens: int = 1200, timeout: float = 30.0):
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise LLMError(
                "anthropic SDK not installed; `pip install 'impacto[llm]'`"
            ) from exc
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
        self.model = model
        self.max_tokens = max_tokens

    # ------------------------------------------------------------------
    def _kwargs(self, system: str, user: str) -> dict:
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "output_config": {"effort": _EFFORT},
            "messages": [{"role": "user", "content": user}],
        }

    def complete(self, system: str, user: str) -> str:
        try:
            msg = self._client.messages.create(**self._kwargs(system, user))
        except self._anthropic.APIError as exc:
            raise LLMError(f"anthropic request failed: {exc}") from exc

        # A safety classifier can decline with HTTP 200 and an empty content list,
        # so the stop reason has to be checked before reading any block.
        if msg.stop_reason == "refusal":
            raise LLMError("anthropic declined the request")
        return "".join(b.text for b in msg.content if b.type == "text").strip()

    def stream(self, system: str, user: str) -> Iterator[str]:
        try:
            with self._client.messages.stream(**self._kwargs(system, user)) as stream:
                yield from stream.text_stream
                if stream.get_final_message().stop_reason == "refusal":
                    raise LLMError("anthropic declined the request")
        except self._anthropic.APIError as exc:
            raise LLMError(f"anthropic stream failed: {exc}") from exc


__all__ = ["AnthropicProvider"]

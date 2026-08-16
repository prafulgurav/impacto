"""Provider-agnostic contract for the narration layer.

The engine is deliberately *grounded-first*: every user-facing answer is composed
deterministically from retrieved facts before any model is consulted. An LLM only
ever rewrites that composition into fluent prose, under a guardrail. That inversion
is what lets us swap providers freely — no provider is load-bearing, and the app is
fully functional with `IMPACTO_LLM_PROVIDER=none`.
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable

SYSTEM_PROMPT = """You are the narration layer of Impacto, a market-intelligence \
system for Indian equities.

You will receive a set of RETRIEVED FACTS: detected global events, transmission-\
channel definitions, and realised historical event-study statistics. Rewrite them \
into a clear, direct explanation for an informed retail investor in India.

Hard rules:
1. Use ONLY the numbers in the retrieved facts. Never compute, estimate or invent
   a figure. If a number is not given, do not state one.
2. Never predict a future price or direction for any security or index. Never
   suggest buying, selling or holding anything.
3. Always describe statistics as historical and always state the sample size.
4. When the retrieved facts mark a linkage as two-sided or low confidence, say so
   plainly. Do not resolve an ambiguity the data does not resolve.
5. Prefer the mechanism over the correlation: explain WHY the channel transmits.
6. If the retrieved facts do not answer the question, say that directly.

Write in plain prose. No hype, no hedging filler, no emoji. Do not include internal
or system XML tags in your response."""


class LLMError(RuntimeError):
    """Raised when a provider fails. Callers always fall back to the composed answer."""


@runtime_checkable
class LLMProvider(Protocol):
    """The whole surface the explainer needs. Two methods, both allowed to fail."""

    name: str
    model: str

    def complete(self, system: str, user: str) -> str: ...

    def stream(self, system: str, user: str) -> Iterator[str]: ...


class NullProvider:
    """The default. Deterministic mode — no network, no model, no narration.

    Everything in the product works in this mode; only the prose style differs.
    CI runs here, and so does any deployment that has not configured a key.
    """

    name = "none"
    model = "none"

    def complete(self, system: str, user: str) -> str:
        raise LLMError("no LLM provider configured")

    def stream(self, system: str, user: str) -> Iterator[str]:
        raise LLMError("no LLM provider configured")
        yield  # pragma: no cover - makes this a generator for type purposes


__all__ = ["LLMProvider", "LLMError", "NullProvider", "SYSTEM_PROMPT"]

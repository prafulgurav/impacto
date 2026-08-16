"""The narration layer must be swappable and must never be load-bearing.

These tests pin three properties:
  1. Provider selection follows configuration, including the GP_ compatibility shim.
  2. A provider failure degrades to the grounded answer rather than an error.
  3. Non-compliant narration is rejected no matter which provider produced it.
"""
from __future__ import annotations

from importlib.util import find_spec

import pytest

from impacto.config import Settings
from impacto.explain.explainer import Explainer
from impacto.explain.guardrails import DISCLAIMER
from impacto.llm import LLMError, NullProvider, build_llm

# The Anthropic path needs its optional SDK; the Gemini path falls back to REST over
# httpx, so it is always constructible.
needs_anthropic_sdk = pytest.mark.skipif(
    find_spec("anthropic") is None, reason="requires the [llm] extra"
)


class StubProvider:
    """Stands in for Claude or Gemini. Records what it was asked."""

    def __init__(self, name: str, reply: str | None = None, fail: bool = False):
        self.name = name
        self.model = f"{name}-stub"
        self.reply = reply or ""
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if self.fail:
            raise LLMError("boom")
        return self.reply

    def stream(self, system: str, user: str):
        self.calls.append((system, user))
        if self.fail:
            raise LLMError("boom")
        for word in self.reply.split(" "):
            yield word + " "


# ------------------------------------------------------------------ selection
def test_defaults_to_null_provider():
    assert build_llm(Settings()).name == "none"


@pytest.mark.parametrize("provider", ["anthropic", "gemini"])
def test_provider_without_a_key_degrades_to_null(provider):
    assert build_llm(Settings(llm_provider=provider)).name == "none"


def test_unknown_provider_degrades_to_null():
    assert build_llm(Settings(llm_provider="chatgpt-5000")).name == "none"


@needs_anthropic_sdk
def test_auto_prefers_anthropic_when_both_keys_are_set():
    both = Settings(llm_provider="auto", anthropic_api_key="a", gemini_api_key="g")
    llm = build_llm(both)
    assert llm.name == "anthropic"
    assert llm.model == "claude-opus-5"


def test_auto_falls_through_to_gemini_then_none():
    gemini_only = Settings(llm_provider="auto", gemini_api_key="g")
    assert build_llm(gemini_only).name == "gemini"

    neither = Settings(llm_provider="auto")
    assert build_llm(neither).name == "none"


def test_gemini_provider_builds_and_reports_its_model():
    llm = build_llm(Settings(llm_provider="gemini", gemini_api_key="g"))
    assert llm.name == "gemini"
    assert llm.model == "gemini-2.5-flash"


def test_model_resolution_is_most_specific_first():
    s = Settings(llm_model="shared-override", gemini_model="gemini-specific")
    assert s.resolved_llm_model("gemini") == "gemini-specific"
    assert s.resolved_llm_model("anthropic") == "shared-override"
    assert Settings().resolved_llm_model("anthropic") == "claude-opus-5"


def test_legacy_gp_prefix_still_configures_the_app(monkeypatch):
    from impacto.config import get_settings, reset_settings_cache

    monkeypatch.setenv("GP_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GP_GEMINI_API_KEY", "legacy-key")
    reset_settings_cache()
    try:
        s = get_settings()
        assert s.llm_provider == "gemini"
        assert s.gemini_api_key == "legacy-key"
    finally:
        reset_settings_cache()


def test_explicit_impacto_prefix_wins_over_legacy(monkeypatch):
    from impacto.config import get_settings, reset_settings_cache

    monkeypatch.setenv("GP_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("IMPACTO_LLM_PROVIDER", "anthropic")
    reset_settings_cache()
    try:
        assert get_settings().llm_provider == "anthropic"
    finally:
        reset_settings_cache()


# ------------------------------------------------------------------ behaviour
def _explainer(service, provider) -> Explainer:
    return Explainer(service.kb, service.impact, service.analogs, service.history, provider)


def test_null_provider_yields_the_grounded_answer(service):
    ex = _explainer(service, NullProvider())
    out = ex.explain("why did IT stocks fall?", as_of=service.latest_event_date())
    assert out.used_llm is False
    assert out.answer.strip()
    assert out.disclaimer == DISCLAIMER


@pytest.mark.parametrize("provider_name", ["anthropic", "gemini"])
def test_compliant_narration_is_adopted_by_either_provider(service, provider_name):
    stub = StubProvider(
        provider_name,
        reply=(
            "Historically, across 12 past occurrences of this archetype, the median "
            "cumulative abnormal return was -180 bps."
        ),
    )
    out = _explainer(service, stub).explain(
        "why did IT stocks fall?", as_of=service.latest_event_date()
    )
    assert out.used_llm is True
    assert "-180 bps" in out.answer
    assert stub.calls, "provider should have been consulted"


@pytest.mark.parametrize("provider_name", ["anthropic", "gemini"])
def test_provider_failure_falls_back_to_grounded_answer(service, provider_name):
    grounded = _explainer(service, NullProvider()).explain(
        "why did IT stocks fall?", as_of=service.latest_event_date()
    )
    out = _explainer(service, StubProvider(provider_name, fail=True)).explain(
        "why did IT stocks fall?", as_of=service.latest_event_date()
    )
    assert out.used_llm is False
    assert out.answer == grounded.answer


def test_non_compliant_narration_is_rejected(service):
    stub = StubProvider("anthropic", reply="NIFTY IT will fall further. Sell IT stocks now.")
    out = _explainer(service, stub).explain(
        "why did IT stocks fall?", as_of=service.latest_event_date()
    )
    assert out.used_llm is False
    assert "Sell IT stocks" not in out.answer


def test_narration_stream_produces_tokens(service):
    stub = StubProvider("gemini", reply="Historically the median move was small.")
    ex = _explainer(service, stub)
    facts, _ = ex.compose("why did IT stocks fall?", as_of=service.latest_event_date())
    assert "".join(ex.narrate_stream("q", facts)).strip().startswith("Historically")


def test_switching_provider_does_not_change_the_grounded_answer(service):
    """The composed answer is the product; the provider is a style layer."""
    a = _explainer(service, StubProvider("anthropic", fail=True))
    g = _explainer(service, StubProvider("gemini", fail=True))
    day = service.latest_event_date()
    assert a.explain("why did IT stocks fall?", as_of=day).answer == (
        g.explain("why did IT stocks fall?", as_of=day).answer
    )

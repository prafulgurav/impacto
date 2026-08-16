"""Compliance guardrails.

If these tests fail, the product is potentially operating as an unregistered
research analyst under SEBI rules. Treat a failure here as a release blocker.
"""
from __future__ import annotations

import pytest

from impacto.explain.guardrails import ComplianceViolation, check_output, enforce

BLOCKED = [
    "You should buy Infosys before the next quarter.",
    "We recommend selling NIFTY Bank on this news.",
    "Infosys will rise sharply after this announcement.",
    "Expect NIFTY IT to rally over the coming weeks.",
    "Price target of Rs 1,850 for TCS.",
    "This is a multibagger opportunity.",
    "Guaranteed returns from this sector rotation.",
    "Book profits in metals now.",
    "The stock is going to surge from here.",
    "Strong buy rating on Reliance.",
]

ALLOWED = [
    "Across 12 past H-1B tightening events, NIFTY IT recorded a median cumulative "
    "abnormal return of -180 bps over the T+0..T+10 window.",
    "A weaker rupee raises the INR value of USD-denominated revenue, which is why "
    "IT services margins historically expanded during dollar strength episodes.",
    "The linkage is two-sided: the mechanism can cut either way depending on the "
    "cause of the rate move.",
    "OPEC+ supply cuts have historically compressed oil marketing company margins "
    "because retail pricing does not adjust immediately.",
    "This distribution is not statistically distinguishable from zero, so the "
    "linkage should be treated as weak evidence.",
    "The sample size is 11 and the observed p-value was 0.002.",
]


@pytest.mark.parametrize("text", BLOCKED)
def test_blocks_advice_and_forecasts(text):
    result = check_output(text, strict=True)
    assert not result.passed, f"guardrail failed to block: {text!r}"
    assert result.flags


@pytest.mark.parametrize("text", ALLOWED)
def test_allows_historical_statements(text):
    result = check_output(text, strict=True)
    assert result.passed, f"guardrail wrongly blocked: {text!r} -> {result.flags}"


def test_redaction_removes_only_the_offending_sentence():
    text = (
        "Across 14 past events NIFTY Bank recorded a median abnormal return of -90 bps. "
        "You should sell your bank holdings today. "
        "The transmission channel is foreign portfolio flow."
    )
    result = check_output(text, strict=False)
    assert "[redacted" in result.redacted_text
    assert "median abnormal return of -90 bps" in result.redacted_text
    assert "foreign portfolio flow" in result.redacted_text
    assert "sell your bank holdings" not in result.redacted_text


def test_enforce_returns_clean_text_unchanged():
    clean = ALLOWED[0]
    assert enforce(clean) == clean


def test_raise_if_failed():
    with pytest.raises(ComplianceViolation):
        check_output("You should buy this now.", strict=True).raise_if_failed()


def test_historical_marker_does_not_launder_an_imperative():
    """'Historically you should buy X' must still be blocked."""
    result = check_output("Historically, you should buy IT stocks on this news.", strict=True)
    assert not result.passed

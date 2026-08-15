"""The shared compliance fixture, judged from the Python side.

web/tests/unit/compliance.test.ts runs the identical cases against the TypeScript
port. Two implementations of the same regex set drift apart otherwise, and the
drift is silent — which for the control that keeps this product on the legal side
of SEBI's advice line is the worst possible failure mode.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from impacto.explain.guardrails import check_output

FIXTURE = Path(__file__).resolve().parents[1] / "lib" / "compliance-fixtures.json"
CASES = json.loads(FIXTURE.read_text())


@pytest.mark.parametrize(
    "text,why",
    [(c["text"], c["why"]) for c in CASES["blocked"]],
    ids=[c["why"] for c in CASES["blocked"]],
)
def test_blocked_cases_are_blocked(text: str, why: str) -> None:
    result = check_output(text, strict=True)
    assert not result.passed, f"should have been blocked ({why}): {text!r}"


@pytest.mark.parametrize(
    "text,why",
    [(c["text"], c["why"]) for c in CASES["allowed"]],
    ids=[c["why"] for c in CASES["allowed"]],
)
def test_allowed_cases_pass(text: str, why: str) -> None:
    result = check_output(text, strict=True)
    assert result.passed, f"wrongly flagged ({why}): {text!r} -> {result.flags}"


def test_fixture_has_enough_cases_to_be_meaningful() -> None:
    assert len(CASES["blocked"]) >= 10
    assert len(CASES["allowed"]) >= 10


def test_fixture_is_the_file_the_typescript_side_reads() -> None:
    """A moved fixture would leave one side testing nothing. Pin the path."""
    assert FIXTURE.exists()
    ts_test = (
        Path(__file__).resolve().parents[1]
        / "web"
        / "tests"
        / "unit"
        / "compliance.test.ts"
    )
    assert "compliance-fixtures.json" in ts_test.read_text()

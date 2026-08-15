"""Compliance guardrails for generated text.

India-specific and load-bearing. Under the SEBI (Research Analyst) Regulations
2014 and the SEBI (Investment Advisers) Regulations 2013, telling a user to buy,
sell or hold a named security — or predicting its price — is a regulated activity
requiring registration. An unregistered app that does it is not "a product with a
disclaimer problem", it is operating illegally.

So the boundary is enforced in code, not in a footer:

  ALLOWED   describing what happened historically, with a measured statistic
            ("NIFTY IT's median 5-day abnormal return across 12 past H-1B
            tightening events was -180bps")
  ALLOWED   explaining a transmission mechanism ("a weaker INR raises the INR
            value of USD-denominated revenue")
  BLOCKED   any forward-looking directional claim about a named security or index
            ("Infosys will fall", "expect NIFTY Bank to drop", "target 1,450")
  BLOCKED   any imperative to trade ("buy", "sell", "book profits", "accumulate")

This module is a defence-in-depth backstop, not the primary control. The primary
control is architectural: the explainer is only ever given retrieved historical
facts to work with, and is instructed to refuse forward-looking questions. See
COMPLIANCE.md for the full control set, and note that a real deployment needs
qualified Indian legal review — this file encodes an engineering team's reading
of the rules, which is not a legal opinion.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

DISCLAIMER = (
    "Impacto presents historical statistics and economic mechanisms for "
    "information and education only. It is not investment advice, not a research "
    "recommendation, and makes no claim about future prices. Past abnormal returns "
    "do not predict future returns. Consult a SEBI-registered investment adviser "
    "before making any investment decision."
)

# Imperatives to transact.
#
# Note the deliberate narrowness. A naive `\b(buy|sell)\b` blocklist is what most
# teams ship and it is useless here: the transmission map legitimately contains
# sentences like "low foreign ownership means there is little to sell". Blocking
# those would either break the product or, worse, train the team to disable the
# guardrail. So the trade verbs are only flagged in an ADVISORY CONTEXT —
# sentence-initial imperative, or governed by a recommendation verb.
_TRADE_VERB = r"(?:buy|sell|short|accumulate|offload|exit|book\s+profits?|square\s+off)"
_ACTION_PATTERNS = [
    # explicit recommendation framing
    r"\b(?:you|investors?|traders?|one)\s+(?:should|must|ought\s+to|can)\s+" + _TRADE_VERB,
    r"\b(?:we|i)\s+(?:recommend|suggest|advise)\b",
    r"\badvise\s+(?:you|investors?|clients?)\s+to\b",
    r"\bour\s+(?:advice|recommendation|call)\s+is\b",
    # sentence-initial imperative: "Buy IT stocks." / "Book profits in metals now."
    r"(?:^|(?<=[.!?]\s)|(?<=[.!?]\s\s))" + _TRADE_VERB + r"\b",
    # analyst-style rating language
    r"\b(?:strong\s+)?(?:buy|sell|hold)\s+(?:rating|call|recommendation)\b",
    r"\b(?:time|right\s+time)\s+to\s+" + _TRADE_VERB,
    r"\b(?:go\s+long|go\s+short)\b",
]

# Forward-looking directional claims.
_FORECAST_PATTERNS = [
    r"\b(?:will|shall)\s+(?:likely\s+)?(?:rise|fall|drop|surge|crash|rally|decline|jump|plunge|gain|lose)\b",
    r"\bis\s+(?:going\s+to|about\s+to)\s+(?:rise|fall|drop|surge|rally|decline)\b",
    r"\b(?:expect|anticipate|forecast|predict|project)(?:s|ed|ing)?\s+(?:a\s+|an\s+|the\s+)?"
    r"(?:\w+\s+){0,3}(?:to\s+)?(?:rise|fall|drop|surge|rally|decline|gain|lose|move)\b",
    r"\b(?:price\s+)?target\s+(?:of\s+)?(?:rs\.?|₹|inr)\s*[\d,]+",
    r"\b(?:upside|downside)\s+of\s+\d+\s*%",
    r"\bguaranteed\s+(?:returns?|profits?)\b",
    r"\b(?:multibagger|sure\s+shot|can't\s+lose|risk[-\s]free\s+returns?)\b",
]

_ACTION_RE = [re.compile(p, re.IGNORECASE) for p in _ACTION_PATTERNS]
_FORECAST_RE = [re.compile(p, re.IGNORECASE) for p in _FORECAST_PATTERNS]

# Phrases that make an otherwise-forward-looking sentence historical.
_HISTORICAL_MARKERS = re.compile(
    r"\b(?:historic(?:al|ally)|in the past|previously|past occurrences?|"
    r"observed|realised|realized|median|mean|average|sample|backtest|"
    r"event stud(?:y|ies)|has\s+(?:historically\s+)?(?:moved|fallen|risen))\b",
    re.IGNORECASE,
)


@dataclass
class GuardrailResult:
    passed: bool
    flags: list[str] = field(default_factory=list)
    redacted_text: str = ""

    def raise_if_failed(self) -> None:
        if not self.passed:
            raise ComplianceViolation("; ".join(self.flags))


class ComplianceViolation(RuntimeError):
    """Raised when generated text crosses the information/advice boundary."""


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def check_output(text: str, strict: bool = True) -> GuardrailResult:
    """Scan generated text for advice-like or forward-looking language.

    Sentences carrying an explicit historical marker are exempt from the forecast
    check — 'NIFTY IT historically fell 180bps' is a statement of fact, not a
    prediction. Action imperatives are never exempt.
    """
    flags: list[str] = []
    kept: list[str] = []

    for sent in _sentences(text):
        sent_flags: list[str] = []
        for rx in _ACTION_RE:
            if rx.search(sent):
                sent_flags.append(f"action_language:{rx.pattern[:40]}")
        if not _HISTORICAL_MARKERS.search(sent):
            for rx in _FORECAST_RE:
                if rx.search(sent):
                    sent_flags.append(f"forward_looking:{rx.pattern[:40]}")
        if sent_flags:
            flags.extend(sent_flags)
            kept.append("[redacted: non-compliant statement removed]")
        else:
            kept.append(sent)

    redacted = " ".join(kept)
    passed = not flags if strict else True
    return GuardrailResult(passed=passed, flags=flags, redacted_text=redacted)


def enforce(text: str, strict: bool = True) -> str:
    """Return compliant text, redacting offending sentences rather than failing hard."""
    result = check_output(text, strict=False)
    if result.flags and strict:
        return result.redacted_text
    return text


__all__ = [
    "check_output",
    "enforce",
    "GuardrailResult",
    "ComplianceViolation",
    "DISCLAIMER",
]

# Compliance

> **This document encodes an engineering team's reading of Indian securities
> regulation. It is not legal advice and is not a legal opinion. Obtain qualified
> Indian counsel before making this product available to real users.**

## The regulatory reality

| Instrument | Relevance |
|---|---|
| SEBI (Research Analysts) Regulations, 2014 — last amended 16 Dec 2024 | Publishing research reports with buy/sell/hold calls or price targets on securities requires RA registration. |
| SEBI (Investment Advisers) Regulations, 2013 — amended Feb, Aug and Nov 2025 | Personalised investment advice requires IA registration. Actively amended through late 2025; treat as a moving target. |
| Finfluencer framework (2024–25) | Regulated entities are barred from association with unregistered persons giving securities recommendations or making performance claims. "Association" is defined broadly, reportedly including technology-system interaction. |
| Three-month lookback restriction | Educational content referencing a named security's price data from the preceding three months risks being read as an implied recommendation. |
| SEBI AI/ML consultation paper (20 Jun 2025) | Proposes mandatory disclosure of AI/ML use, a **named senior accountable officer**, ≥5 years of documentation retention, independent external fairness audits, and — critically — that **outsourcing an AI vendor does not transfer liability**. |

**Open question you must verify before building on this**: as of our research the
June 2025 AI/ML consultation had not been confirmed as a finalised, binding
circular. Check sebi.gov.in's live circular list. That single fact is the
difference between "guidance we should follow" and "binding obligation with an
accountable officer attached."

## The line this product draws

| | Example |
|---|---|
| **ALLOWED — historical fact** | "Across 12 past H-1B tightening events, NIFTY IT recorded a median cumulative abnormal return of −180 bps over T+0..T+10." |
| **ALLOWED — mechanism** | "A weaker rupee raises the INR value of USD-denominated revenue; roughly +1% USDINR adds ~30–40 bps to IT services EBIT margin pre-hedge." |
| **ALLOWED — stated uncertainty** | "This distribution is not statistically distinguishable from zero, so the linkage should be treated as weak evidence." |
| **BLOCKED — forward-looking on a named security** | "Infosys will fall", "expect NIFTY Bank to drop", "target ₹1,850 for TCS" |
| **BLOCKED — transact imperative** | "buy", "sell", "book profits", "accumulate", "strong buy rating" |

## The control set

Compliance is **architectural first, filtered second**. In order of load-bearing:

1. **The system has no forecasting capability.** There is no model that outputs a
   future price or direction. `AnalogEngine` returns a distribution of *realised
   past* outcomes. You cannot leak a forecast the system cannot compute.
2. **The LLM never sees raw data, only retrieved facts.** `Explainer` composes a
   complete grounded answer first; the LLM rewrites it, is instructed it may not
   compute or invent any number, and is forbidden from predicting. If the LLM is
   unavailable or non-compliant, the system falls back to the composed answer —
   it never degrades to an ungrounded one.
3. **The guardrail filter** (`explain/guardrails.py`) scans all generated text and
   blocks advisory or forward-looking language. Regex-based, therefore
   defeatable — which is why it is control #3, not control #1.
4. **Portfolio features report exposure, never action.**
   `ImpactEngine.portfolio_exposure` says *"X% of your portfolio sits in sectors
   this archetype has historically moved."* It does not say what to do about it.
   That distinction is the entire product boundary.
5. **Uncertainty is surfaced, not smoothed.** Two-sided rules stay two-sided.
   p-values above 0.10 are labelled as weak evidence in the output text. Alert
   severity is downgraded when the analog distribution is noise.
6. **Every claim is cited.** `Explanation.citations` carries the event, the
   transmission rule, and the event-study statistics behind every sentence.
7. **Disclaimer on every user-facing surface** — alerts, digests, explanations,
   API responses, dashboard.

## Why the guardrail is narrow on purpose

A naive `\b(buy|sell)\b` blocklist is what most teams ship, and it is worse than
useless here. The transmission map legitimately contains:

> "Relative outperformer during FII-led selloffs because low foreign ownership
> means little to sell and DII/retail flow dominates the register."

A blunt blocklist flags that. Two things then happen, both bad: the product breaks
on legitimate content, and the team learns to disable the guardrail. So trade verbs
are flagged only in **advisory context** — sentence-initial imperative, or governed
by a recommendation verb ("you should sell", "we recommend", "time to buy").

Symmetrically, forward-looking patterns are exempted when the sentence carries an
explicit historical marker ("historically", "median", "across N past occurrences"),
because *"NIFTY IT historically fell 180 bps"* is a statement of fact. But an
imperative is **never** exempted — `test_historical_marker_does_not_launder_an_imperative`
asserts that "Historically, you should buy IT stocks" is still blocked.

## If you deploy this

- [ ] Verify the current status of SEBI's AI/ML framework on sebi.gov.in
- [ ] Obtain a written legal opinion on the information/advice boundary for your
      specific copy and UX, not just the engine
- [ ] Decide whether to seek RA or IA registration — it materially widens what you
      can ship
- [ ] Name a senior accountable officer for the AI/ML lifecycle
- [ ] Implement ≥5-year audit logging of every generated output and its citations
- [ ] Disclose AI/ML use to users in plain language
- [ ] Review the three-month price-lookback restriction against your UI
- [ ] Consider SEBI's regulatory sandbox / Safe Space for a supervised pilot
- [ ] Set up an independent review of output fairness and accuracy
- [ ] Confirm your market data licence permits the display you are building

## Non-Indian jurisdictions

`GP_JURISDICTION` exists but only `IN` is implemented. The guardrail patterns
encode Indian regulatory categories. Do not assume they transfer.

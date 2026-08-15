# ADR-0001: The transmission map is hand-authored code, not a learned model

**Status:** accepted · **Date:** 2026-08-15

## Context

The core question — which Indian sectors does a given global event reach, and
through what mechanism — could be answered by (a) supervised learning on
historical event/return pairs, (b) an LLM reasoning zero-shot per event, or
(c) a hand-authored causal knowledge base scored against data.

## Decision

(c). `knowledge/transmission_map.yaml` is version-controlled, schema-validated,
test-covered, and calibrated against realised event studies.

## Rationale

- **Sample size.** ~40 distinct OPEC decisions and ~30 US-India trade actions
  exist in the modern era. That is a case list, not a training set. A learned
  model on 40 examples memorises rather than generalises.
- **Non-stationarity.** NIFTY Bank's FII-ownership structure in 2015 is not its
  structure in 2026. A learned correlation silently assumes it is.
- **Auditability.** SEBI's proposed AI/ML framework requires a named accountable
  officer, 5-year documentation, and independent fairness audits. "The embedding
  said so" does not survive that review. A YAML rule with a written rationale and
  a git blame does.
- **The valuable output is a distinction, not an average.** "OMC down, upstream
  oil up, under the same event" is exactly what a correlation model destroys by
  pooling them as "energy." That distinction is the product.
- **It is arguable.** A domain expert can read a rule, disagree, and open a PR.
  Nobody can meaningfully argue with a weight matrix.

## Consequences

- **Positive:** every output traces to a citable rule; the map is a reviewable
  artefact; new archetypes are cheap; the calibration report gives an honest,
  quantitative view of which beliefs are supported.
- **Negative:** coverage is bounded by author effort; the map encodes one team's
  reading of market structure; it will not discover a linkage nobody thought of.
- **Mitigation:** `impacto calibrate` scores every prior against realised
  history and labels contradictions. `test_calibration_report_is_honest` asserts
  the report can say "contradicted" — a 100%-confirmed report is a bug, not a win.

## Alternatives rejected

- **End-to-end learned mapping** — see sample size and auditability above.
- **LLM zero-shot per event** — non-deterministic, uncitable, and it hallucinates
  plausible-sounding channels. It is used here only as a narration layer over
  retrieved facts (ADR-0004).
- **Pure sentiment scoring** — the dominant published approach for Indian market
  NLP, and structurally incapable of producing the OMC/upstream-oil divergence.

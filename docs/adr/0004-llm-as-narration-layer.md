# ADR-0004: The LLM narrates; it does not decide

**Status:** accepted · **Date:** 2026-08-15

## Context

An LLM could plausibly own any of: classifying headlines into archetypes,
reasoning about which sectors an event affects, or explaining a market move.

## Decision

It owns **none of them as primary**. Order of operations is retrieve, compose,
narrate:

1. **Retrieve** — deterministic code finds active archetypes, their transmission
   rules, and realised event-study statistics.
2. **Compose** — deterministic code builds a complete, fully-cited answer. This
   answer ships as-is if anything downstream fails.
3. **Narrate** — an LLM rewrites step 2 into prose. It sees only the retrieved
   facts, is instructed it may not compute or invent any number, and is forbidden
   from predicting. Its output passes through the compliance guardrail.

If the LLM is unconfigured, unavailable, or its output fails the guardrail, the
system returns the step-2 answer. **It never degrades to an ungrounded answer.**

The one other LLM role is adjudicating *ambiguous* classifications — and it may
only choose among archetypes the lexical scorer already surfaced. It cannot
invent one.

## Rationale

- **Compliance.** SEBI's proposed AI/ML framework makes the deploying entity fully
  responsible for AI output, including a vendor's. An LLM that can emit an
  unreviewed number about a security is an unbounded liability. One that can only
  rephrase pre-computed, pre-cited facts is bounded.
- **Auditability.** Every sentence traces to a retrieved fact and a citation.
- **Determinism where it matters.** Classification and impact scoring are
  reproducible; only prose style varies.
- **It degrades well.** The product is fully functional with `GP_LLM_PROVIDER=none`,
  which is also how CI runs.

## Consequences

- Prose is less fluent than a free-running LLM would produce. Accepted.
- Novel linkages absent from the transmission map are not discovered. Accepted —
  that is what human contribution and the calibration report are for.
- Template quality is now a first-class product concern, since the templates *are*
  the product.

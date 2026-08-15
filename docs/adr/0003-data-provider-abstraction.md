# ADR-0003: Market data behind an interface, with a deterministic fixture default

**Status:** accepted · **Date:** 2026-08-15

## Context

Every free Indian equity data source is an unofficial scraper of NSE's website:
`jugaad-data`, `nsetools`, `nsepython`, and `yfinance`'s `.NS` tickers. All break
when NSE changes its site internals or tightens anti-bot controls. `investpy`, a
plausible cross-market alternative, is abandoned — its own README says so.
Broker APIs (Kite Connect, ~Rs 500/month) are reliable but require KYC and a live
trading account, which is a hard gate for an open-source repo.

## Decision

`MarketProvider` is an abstract interface with `prices()` and `returns()`. Two
implementations ship. **`FixtureProvider` is the default.**

`FixtureProvider` builds deterministic synthetic series from a fixed seed:
benchmark GBM + per-symbol beta exposure + idiosyncratic noise + **injected event
effects** read from `data/fixtures/events.json`.

## Rationale

- **Ground truth for testing.** Injected CARs mean `tests/test_eventstudy.py` can
  assert the engine *recovers a known answer*. With real data an event-study
  implementation is untestable and every downstream number is unverified.
- **Hermetic CI.** No network, no rate limits, no flakes, no vendor outage
  breaking the build.
- **No licensing question.** Redistributing NSE/vendor price history in a public
  repo has real legal exposure. Synthetic data has none.
- **Honest demo.** A reviewer clones and runs in 30 seconds without an API key.
- **The swap point is explicit.** Production implements one interface.

## Consequences

- Numbers in the demo are **not real market history** and are labelled as such in
  every fixture record ("Synthetic fixture event. Not a real historical
  occurrence.").
- The fixture generator deliberately injects prior-contradicting effects for ~20%
  of rules, so the calibration report produces a realistic mixed result rather
  than a vanity 100%-confirmed one.
- A bug found while building this: the per-symbol seed originally derived from
  Python's builtin `hash()`, which is salted per process — making the
  "deterministic" provider non-deterministic across runs and every numeric
  assertion silently unreproducible. Now `zlib.crc32`, pinned by
  `test_fixture_provider_is_actually_deterministic`.

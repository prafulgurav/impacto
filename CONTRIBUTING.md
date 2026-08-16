# Contributing

The highest-value contribution is **a rule in the transmission map** — a new event
archetype, a corrected direction, a better rationale, or the deletion of a rule the
data contradicts. Code contributions are welcome; domain contributions are what
make this repo worth anything.

## Adding or changing a transmission rule

Edit `knowledge/transmission_map.yaml`. A rule PR must:

1. **Cite a channel** from `channels.yaml`. If the mechanism doesn't fit an
   existing channel, add one — but a new channel needs its own justification.
2. **Explain the mechanism in the rationale**, not just assert a direction. "Banks
   fall on Fed hikes" is not a rationale. "Highest FII ownership in the index and
   the most liquid vehicle for foreign de-risking, so it absorbs the first wave of
   outflow" is.
3. **Grade confidence honestly.** `high` means the mechanism is near-mechanical
   *and* a decent historical sample exists. Most rules are `medium`.
4. **Use `direction: 0` when the effect is genuinely two-sided.** Resolving a real
   ambiguity to look confident is the single worst thing you can do to this repo.
5. **Run the calibration report** and paste the relevant rows into the PR:
   ```
   make calibrate
   ```

`make test` enforces the mechanical rules (channel exists, target resolves,
rationale depth, sign consistency, inverse archetypes actually oppose). Reviewers
enforce the rest.

## Deleting a rule

A PR that removes a rule the calibration report labels `contradicted`, with the
report output attached, will be merged fast. That is the point of the report.

## Adding a market data provider

Implement `MarketProvider` (`src/impacto/market/provider.py`) — `prices()` is
the only required method — and register it in `_PROVIDERS`. Kite Connect, Upstox,
Angel One SmartAPI, Dhan and EODHD are all wanted.

## Standards

- `make lint` and `make test` must pass. CI runs both on 3.11 and 3.12.
- CI also regenerates the fixture corpus and fails on any diff. If your change
  makes the pipeline non-deterministic, that check catches it.
- New user-facing text must pass the compliance guardrail. Add a test.
- ADRs (`docs/adr/`) for anything that changes an architectural assumption.

## What will not be merged

- Price predictions, target prices, buy/sell signals, or anything that moves the
  product across the SEBI information/advice line. See COMPLIANCE.md.
- Removing or weakening the compliance guardrail without a documented legal basis.
- A learned model replacing the transmission map — see ADR-0001 for why, and open
  an ADR if you want to argue the other side.

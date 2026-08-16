# Roadmap

Ordered by "what would make this genuinely useful," not by what is easy.

## Now — v0.1 (shipped)

- 15 event archetypes, 11 transmission channels, 55 impact rules
- Market-model event study with CAR/CAAR and significance testing
- Historical analog distributions ("what happened last time")
- Calibration report scoring every prior against realised history
- Alerts, daily digest, grounded explainer, FastAPI + dashboard
- Compliance guardrails enforced in code and covered by tests

## Next — v0.2: make the numbers real

The single most important gap. Everything else is polish until this is done.

1. **A production market data provider.** Kite Connect implementation of
   `MarketProvider`, plus an EODHD fallback. NSE bhavcopy loader for EOD history.
2. **A real historical event corpus.** Hand-curate dated occurrences of each
   archetype from 2010 onward — FOMC decisions with surprise magnitudes from fed
   funds futures, OPEC+ announcements, USTR actions, H-1B rule changes. This is
   research work, not engineering work, and it is what turns the priors from
   hypotheses into calibrated estimates.
3. **Re-fit every prior** from the calibration report and delete what the data
   rejects. Expect to lose several rules. That is success, not failure.

## Then — v0.3: better inference

4. **Surprise magnitude from market data.** Currently populated only in fixtures.
   Derive it from fed funds futures repricing, consensus-vs-actual for CPI/NFP,
   and n-session commodity moves — the archetypes already declare the rules in
   their `surprise_rule` fields.
5. **FII/DII flow ingestion.** The `fii_flow` channel is cited by 9 rules but has
   no live observable feeding it. NSE publishes daily provisional figures.
6. **Regime conditioning.** The same archetype behaves differently in a
   risk-on versus risk-off regime. Condition analog selection on India VIX,
   USDINR trend and FII flow state, and report conditional distributions.
7. **HAC standard errors** behind a flag, plus a bootstrap CAR distribution, to
   address the variance assumption documented in ADR-0002.
8. **Overlapping-event correction.** Exclude or down-weight analogs whose event
   window overlaps another archetype's, and report how many were dropped.

## Later — v0.4: coverage and product

9. **More archetypes**: RBI policy surprises, EU CBAM, US FDA actions on Indian
   plants, monsoon/IMD forecasts, GIFT City and FPI rule changes, sovereign
   rating actions, index inclusion (JPM GBI-EM, MSCI rebalances).
10. **Stock-level idiosyncratic overlay.** Sector membership is a coarse proxy.
    Company-level USD revenue share, import intensity and hedging policy from
    filings would sharpen the map considerably.
11. **Portfolio exposure UI** on top of the existing `/impact/portfolio` endpoint.
12. **Push alerts and email digest**, with a per-user archetype watchlist.
13. **Hindi and regional language digests.** The audience that most needs this is
    not reading English financial media.

## Explicitly out of scope

- Order execution, position sizing, portfolio optimisation
- Price targets, buy/sell signals, forecast models
- Anything that requires RA or IA registration to ship legally, unless the
  project actually obtains it

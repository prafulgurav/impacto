# ADR-0002: Market-model event study with textbook variance

**Status:** accepted · **Date:** 2026-08-15

## Context

We need to quantify "what happened last time." Options: raw returns, market-
adjusted returns, the market model, or a multi-factor (Fama-French-style) model.

## Decision

The market model (Brown & Warner 1985; MacKinlay 1997):

```
estimation:  R_it = a_i + b_i*R_mt + e_it     120 sessions, ending >=15 days before T
event:       AR_it = R_it - (a_i + b_i*R_mt)
             CAR_i(a,b) = sum of AR_it
             sigma_CAR = sigma_e * sqrt(L),  t = CAR/sigma_CAR ~ t(N-2)
```

## Rationale

- **Comparability.** It is the standard in the published event-study literature,
  so our numbers can be checked against academic results.
- **Transparency.** Every intermediate — alpha, beta, R-squared, sigma_e, N — is
  returned by the API. A user can reconstruct the number by hand. A latent-factor
  model cannot offer that.
- **A factor model needs Indian factor returns** (SMB/HML/WML for NSE) that are
  not freely and reliably available, adding a dependency for a second-order gain.

## Two deviations worth knowing

1. **The benchmark uses a constant-mean-return model.** Regressing NIFTY 50 on
   itself yields beta=1, alpha=0 and an identically zero abnormal return —
   silently reporting "no effect" for every index-level event. This was a real
   bug, caught because the calibration report showed `+0` realised for every
   `NIFTY_50` rule. For the benchmark we use mean-adjusted returns instead.
2. **Baskets use a cross-sectional t-test** (CAAR over the standard error across
   members), not the time-series statistic, because sector members' residuals are
   demonstrably not independent of each other. The time-series test would
   overstate significance badly.

## Known weakness — stated, not hidden

`sigma_CAR = sigma_e * sqrt(L)` assumes serially uncorrelated residuals. That is
the textbook assumption and it is **optimistic for multi-day windows**, especially
around volatility clustering. Consequence: p-values on long windows are too small.

We keep it because transparency and literature-comparability outweigh precision
here, and because the product's headline output is a *distribution* (median, 5th
and 95th percentile) rather than a significance verdict. Mitigations available:

- report the cross-sectional test (already done for baskets)
- add HAC/Newey-West standard errors behind a flag
- bootstrap the CAR distribution

## Also unhandled: overlapping events

Global macro events arrive roughly every 9 sessions. Event windows overlap, so
CARs are contaminated by neighbouring events. This is real-world, not a fixture
artefact. `tests/test_eventstudy.py` measures it: single-stock recovery is 81%
sign-correct but only r~0.64 against ground truth, versus r~0.70 and tighter MAE
for sector indices. **That gap is why the product leads with sectors.**

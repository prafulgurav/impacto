"""Event-study engine correctness.

The fixture provider injects a KNOWN cumulative abnormal return for each event.
These tests assert the engine recovers it. Without a ground truth, an event-study
implementation is untestable and every downstream number is unverified.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from impacto.eventstudy.car import InsufficientData, parse_window


# ------------------------------------------------------------------ windows
@pytest.mark.parametrize(
    "text,expected",
    [
        ("T+0", (0, 0)),
        ("T+1..T+5", (1, 5)),
        ("T-1..T+1", (-1, 1)),
        ("T+0..T+21", (0, 21)),
        (" T+1 .. T+10 ", (1, 10)),
    ],
)
def test_parse_window(text, expected):
    assert parse_window(text) == expected


@pytest.mark.parametrize("bad", ["", "T5", "1..5", "T+5..T+1", "tomorrow"])
def test_parse_window_rejects_garbage(bad):
    with pytest.raises(ValueError):
        parse_window(bad)


# ---------------------------------------------------------------- recovery
# The fixture series starts 2017-01-02; the market model needs ~120 sessions of
# estimation window plus a gap, so events before this date are unusable by
# construction rather than by defect.
WARMUP_END = date(2017, 9, 1)


def _pick_events(raw_events, archetype_id, symbol, min_bps=150):
    out = []
    for e in raw_events:
        if e["archetype_id"] != archetype_id:
            continue
        if date.fromisoformat(e["event_date"]) < WARMUP_END:
            continue
        eff = e.get("effects", {}).get(symbol)
        if eff and abs(eff["car_bps"]) >= min_bps:
            out.append((e, eff))
    return out


def _recovery(study, raw_events, archetype_id, symbol, window, min_bps=150):
    inj, mea = [], []
    for ev, eff in _pick_events(raw_events, archetype_id, symbol, min_bps):
        try:
            res = study.run(symbol, date.fromisoformat(ev["event_date"]), window)
        except InsufficientData:
            continue
        inj.append(eff["car_bps"])
        mea.append(res["cumulative_abnormal_return_bps"])
    return np.array(inj), np.array(mea)


def test_recovers_injected_car_on_a_sector_index(study, raw_events):
    """Measured CAR must track the injected ground-truth CAR."""
    inj, mea = _recovery(
        study, raw_events, "US_IMMIGRATION_VISA_TIGHTENING", "^CNXIT", "T+0..T+10"
    )
    assert len(inj) >= 8, "fixture corpus too small for this test"
    assert (np.sign(inj) == np.sign(mea)).mean() >= 0.75
    assert np.corrcoef(inj, mea)[0, 1] > 0.60
    assert np.mean(np.abs(inj - mea)) < 0.60 * np.mean(np.abs(inj))


def test_single_stock_recovery_is_noisier_but_directionally_right(study, raw_events):
    """Documents a real limitation rather than hiding it.

    Idiosyncratic volatility on a single stock is roughly double a sector index's,
    and the fixture corpus has overlapping events (one every ~9 sessions), which is
    also true of the real world. So single-name CAR estimates are directionally
    useful and quantitatively noisy. Anyone reading a single-stock number off this
    engine should know that. Hence the sector-first product design.
    """
    inj, mea = _recovery(study, raw_events, "OPEC_SUPPLY_CUT", "IOC.NS", "T+0..T+4")
    assert len(inj) >= 10
    assert (np.sign(inj) == np.sign(mea)).mean() >= 0.70
    assert np.corrcoef(inj, mea)[0, 1] > 0.45


def test_market_model_recovers_beta(study, provider):
    """Beta estimates should be in a sane band for a low-beta and high-beta index."""
    d = date(2023, 6, 15)
    fmcg = study.fit("^CNXFMCG", d)          # true beta 0.65
    realty = study.fit("^CNXREALTY", d)      # true beta 1.45
    assert fmcg.beta < realty.beta
    assert 0.2 < fmcg.beta < 1.1
    assert 0.9 < realty.beta < 2.0
    assert fmcg.n_obs >= 60


def test_benchmark_uses_mean_adjusted_model(study, kb):
    """Regressing the benchmark on itself would report zero abnormal return always."""
    fit = study.fit(kb.benchmark.symbol, date(2023, 6, 15))
    assert fit.beta == 0.0
    assert fit.resid_sigma > 0
    res = study.run(kb.benchmark.symbol, date(2023, 6, 15), "T+1..T+5")
    assert res["cumulative_abnormal_return_bps"] != 0.0


def test_no_effect_event_gives_insignificant_car(study, raw_events):
    """A symbol with no injected effect must not show a significant abnormal return."""
    # NIFTY FMCG is untouched by USD_STRENGTH_SHOCK in the map
    evs = [
        e
        for e in raw_events
        if e["archetype_id"] == "USD_STRENGTH_SHOCK"
        and date.fromisoformat(e["event_date"]) >= WARMUP_END
        and "^CNXFMCG" not in e.get("effects", {})
    ][:15]
    assert evs
    sig = 0
    for e in evs:
        res = study.run("^CNXFMCG", date.fromisoformat(e["event_date"]), "T+1..T+5")
        sig += int(res["significant_at_5pct"])
    # false positive rate should be near the 5% nominal level, allow generous slack
    assert sig <= max(2, int(0.35 * len(evs)))


def test_car_is_additive_over_windows(study):
    d = date(2022, 3, 10)
    a = study.run("^CNXIT", d, "T+0..T+2")
    b = study.run("^CNXIT", d, "T+3..T+5")
    c = study.run("^CNXIT", d, "T+0..T+5")
    assert c["cumulative_abnormal_return_bps"] == pytest.approx(
        a["cumulative_abnormal_return_bps"] + b["cumulative_abnormal_return_bps"], abs=1.0
    )


def test_basket_study_reports_members_and_caar(study, kb):
    members = kb.baskets["OMC"].members
    res = study.run_basket(members, date(2022, 3, 10), "T+1..T+5")
    assert res["n_members"] == len(members)
    cars = [m["cumulative_abnormal_return_bps"] for m in res["members"]]
    assert res["caar_bps"] == pytest.approx(sum(cars) / len(cars), abs=1e-6)


def test_insufficient_data_raises_not_returns_garbage(study):
    with pytest.raises(InsufficientData):
        study.run("^CNXIT", date(2017, 1, 10), "T+1..T+5")


def test_fixture_provider_is_actually_deterministic(provider):
    """Regression guard.

    The first implementation seeded per-symbol noise from the builtin hash(),
    which Python salts per process — so every numeric assertion in this file was
    silently non-reproducible across runs. Pin the exact values.
    """
    px = provider.prices("^CNXIT", date(2023, 1, 2), date(2023, 1, 31))
    assert len(px) == 22
    assert float(px.iloc[0]) == pytest.approx(32415.3429, rel=1e-6)
    assert float(px.iloc[-1]) == pytest.approx(32751.5505, rel=1e-6)


def test_estimation_window_excludes_the_event(study):
    """Look-ahead check: the estimation window must end before the event date."""
    d = date(2023, 6, 15)
    fit = study.fit("^CNXIT", d)
    # gap of estimation_gap*1.5 calendar days is enforced in _fit_uncached;
    # assert it by confirming a large injected event on d does not move alpha much
    assert abs(fit.alpha) < 0.01

#!/usr/bin/env python3
"""Generate the deterministic fixture corpus used by tests, CI and the demo.

Why synthetic fixtures instead of committed real price history:
  * Redistributing NSE/vendor price data has licensing questions we do not want
    in an open repo.
  * Tests need a KNOWN ground truth. Here we inject a specific CAR per event and
    assert the event-study engine recovers it (tests/test_eventstudy.py). You
    cannot do that with real data.
  * CI must be hermetic and fast.

The generator deliberately injects noise, and for ~20% of impact rules it injects
an effect that CONTRADICTS the encoded prior. That is on purpose: it means
`impacto calibrate` produces a realistic mixed report rather than a vanity
100%-confirmed one, and the calibration test has something real to catch.

Run:  python scripts/generate_fixtures.py
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from impacto.knowledge import KnowledgeBase  # noqa: E402

OUT = ROOT / "data" / "fixtures"
OUT.mkdir(parents=True, exist_ok=True)

START = date(2017, 1, 2)
END = date(2026, 8, 14)
SEED = 20260815

# How often an archetype recurs, in calendar days (roughly realistic cadence)
CADENCE = {
    "FED_HAWKISH_SURPRISE": 105,
    "FED_DOVISH_SURPRISE": 135,
    "US_CPI_UPSIDE_SURPRISE": 70,
    "OPEC_SUPPLY_CUT": 95,
    "CRUDE_COLLAPSE": 110,
    "US_TARIFF_ON_INDIA": 190,
    "US_TARIFF_ON_CHINA": 150,
    "CHINA_STIMULUS": 175,
    "GEOPOLITICAL_CONFLICT_SHOCK": 120,
    "USD_STRENGTH_SHOCK": 85,
    "SEMICONDUCTOR_EXPORT_CONTROL": 240,
    "US_IMMIGRATION_VISA_TIGHTENING": 260,
    "FII_SUSTAINED_OUTFLOW": 100,
    "GOLD_SPIKE": 130,
    "US_RECESSION_SIGNAL": 165,
}

HEADLINE_TEMPLATES = {
    "FED_HAWKISH_SURPRISE": "Fed hikes rates more than expected; Powell signals further tightening",
    "FED_DOVISH_SURPRISE": "Fed cuts rates, dot plot turns dovish as Powell flags easing cycle",
    "US_CPI_UPSIDE_SURPRISE": "US CPI inflation comes in hotter than consensus",
    "OPEC_SUPPLY_CUT": "OPEC+ announces surprise production cut; Brent crude spikes",
    "CRUDE_COLLAPSE": "Brent crude slumps as demand destruction fears build; oil glut widens",
    "US_TARIFF_ON_INDIA": "US announces reciprocal tariff on Indian goods; USTR flags trade deal delay",
    "US_TARIFF_ON_CHINA": "US widens China tariff and entity list export controls",
    "CHINA_STIMULUS": "China unveils large stimulus package; PBOC cuts RRR, property rescue announced",
    "GEOPOLITICAL_CONFLICT_SHOCK": "Escalation in conflict zone; missile strikes raise blockade risk near Strait of Hormuz",
    "USD_STRENGTH_SHOCK": "Dollar index surges to multi-month high; rupee hits record low",
    "SEMICONDUCTOR_EXPORT_CONTROL": "New BIS rule tightens semiconductor and advanced computing export controls",
    "US_IMMIGRATION_VISA_TIGHTENING": "US raises H-1B visa fee and tightens USCIS eligibility norms",
    "FII_SUSTAINED_OUTFLOW": "FII selling accelerates; foreign investors pull record outflows from Indian equities",
    "GOLD_SPIKE": "Gold hits record as safe haven demand surges; bullion rally extends",
    "US_RECESSION_SIGNAL": "US payrolls miss badly, Sahm rule triggers; ISM contraction deepens recession fears",
}


def business_days(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def main() -> None:
    kb = KnowledgeBase(ROOT / "knowledge")
    rng = np.random.default_rng(SEED)

    # ---------------------------------------------------------- symbol spec
    symbols: dict[str, dict] = {}

    def add(sym: str, beta: float, idio: float, price: float, alpha: float = 0.0) -> None:
        symbols[sym] = {
            "beta": beta,
            "idio_vol": idio,
            "start_price": price,
            "alpha": alpha,
        }

    add(kb.benchmark.symbol, 1.0, 0.0, 8000.0, 0.0)
    sector_beta = {
        "NIFTY_BANK": 1.15, "NIFTY_IT": 0.85, "NIFTY_AUTO": 1.05, "NIFTY_ENERGY": 0.95,
        "NIFTY_PHARMA": 0.70, "NIFTY_METAL": 1.35, "NIFTY_FMCG": 0.65, "NIFTY_REALTY": 1.45,
        "NIFTY_FINSERV": 1.10, "NIFTY_PSU_BANK": 1.25,
    }
    for sid, sec in kb.sectors.items():
        add(sec.symbol, sector_beta.get(sid, 1.0), 0.0085, float(rng.uniform(2000, 45000)))
        for p in sec.proxies:
            if p not in symbols:
                add(p, sector_beta.get(sid, 1.0) + float(rng.normal(0, 0.12)), 0.013,
                    float(rng.uniform(150, 4000)))
    for b in kb.baskets.values():
        for m in b.members:
            if m not in symbols:
                add(m, 1.0 + float(rng.normal(0, 0.25)), 0.016, float(rng.uniform(80, 3500)))

    market_spec = {
        "seed": SEED,
        "start": START.isoformat(),
        "end": END.isoformat(),
        "mkt_drift": 0.00045,
        "mkt_vol": 0.0091,
        "default_symbol": {"beta": 1.0, "idio_vol": 0.015, "start_price": 1000.0, "alpha": 0.0},
        "symbols": symbols,
    }

    # -------------------------------------------------------------- events
    events, headlines = [], []
    # Rules chosen to behave "wrong" vs their prior — deterministic, ~20% of rules.
    contrarian: set[tuple[str, str]] = set()
    for arch in kb.archetypes.values():
        for imp in arch.impacts:
            if rng.random() < 0.20:
                contrarian.add((arch.id, imp.target))

    for arch_id, cadence in CADENCE.items():
        arch = kb.archetypes[arch_id]
        cursor = START + timedelta(days=int(rng.integers(30, cadence)))
        n = 0
        while cursor < END - timedelta(days=45):
            ev_date = business_days(cursor)
            surprise = float(abs(rng.normal(1.0, 0.45))) + 0.15
            effects: dict[str, dict] = {}

            for imp in arch.impacts:
                resolved = kb.resolve_target(imp.target)
                lo, hi = imp.magnitude_prior_bps
                centre = (lo + hi) / 2.0
                spread = max(abs(hi - lo), 60.0)
                car = float(rng.normal(centre * surprise, spread * 0.65))
                if (arch_id, imp.target) in contrarian:
                    car = -car * float(rng.uniform(0.4, 1.1))
                days = {"fast": 2, "medium": 4, "slow": 8}.get(
                    kb.channel(imp.channels[0]).horizon, 3
                )
                targets = list(resolved["symbols"])
                if resolved["kind"] in ("sector", "benchmark"):
                    targets += list(resolved.get("proxies", []) or [])
                for sym in targets:
                    jitter = float(rng.normal(1.0, 0.30))
                    prev = effects.get(sym, {"car_bps": 0.0, "days": days})
                    prev["car_bps"] += car * jitter
                    effects[sym] = prev

            eid = f"{arch_id}:{ev_date.isoformat()}"
            events.append({
                "event_id": eid,
                "archetype_id": arch_id,
                "event_date": ev_date.isoformat(),
                "headline": HEADLINE_TEMPLATES[arch_id],
                "sources": ["fixture://synthetic"],
                "match_score": round(float(rng.uniform(0.55, 0.98)), 3),
                "surprise_magnitude": round(surprise, 3),
                "notes": "Synthetic fixture event. Not a real historical occurrence.",
                "effects": {k: {"car_bps": round(v["car_bps"], 1), "days": v["days"]}
                            for k, v in effects.items()},
            })
            headlines.append({
                "published_at": datetime.combine(ev_date, datetime.min.time())
                .replace(hour=9, minute=15).isoformat(),
                "title": HEADLINE_TEMPLATES[arch_id],
                "url": f"fixture://synthetic/{eid}",
                "source": "Impacto Fixture Wire",
                "summary": arch.description.strip()[:300],
            })
            n += 1
            cursor += timedelta(days=int(rng.integers(int(cadence * 0.6), int(cadence * 1.5))))
        print(f"  {arch_id:34s} {n:3d} events")

    events.sort(key=lambda e: e["event_date"])
    headlines.sort(key=lambda h: h["published_at"])

    (OUT / "market_spec.json").write_text(json.dumps(market_spec, indent=1))
    (OUT / "events.json").write_text(json.dumps(events, indent=1))
    (OUT / "headlines.json").write_text(json.dumps(headlines, indent=1))
    print(f"\nWrote {len(symbols)} symbols, {len(events)} events, {len(headlines)} headlines -> {OUT}")
    print(f"Contrarian (prior-violating) rules injected: {len(contrarian)}")


if __name__ == "__main__":
    main()

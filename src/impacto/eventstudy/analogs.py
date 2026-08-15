"""'What happened last time?' — historical analog engine.

This is the Kensho-style capability: given an event archetype and a target, pull
every past occurrence of that archetype, run an event study on each, and return
the OUTCOME DISTRIBUTION rather than a point forecast.

Returning a distribution rather than a prediction is a deliberate product and
compliance choice, not a modelling shortcut. A distribution of realised past
outcomes is historical fact; a point forecast for a named security is a
recommendation under SEBI's Research Analyst regime. See COMPLIANCE.md.
"""
from __future__ import annotations

from datetime import date

import numpy as np
from scipy import stats

from ..knowledge import KnowledgeBase
from ..market.provider import MarketProvider
from ..models import AnalogEvent, AnalogSummary, DetectedEvent
from .car import EventStudy, InsufficientData


class AnalogEngine:
    def __init__(
        self,
        kb: KnowledgeBase,
        provider: MarketProvider,
        event_history: list[DetectedEvent],
    ) -> None:
        self.kb = kb
        self.provider = provider
        self.history = event_history
        self.study = EventStudy(provider, benchmark_symbol=kb.benchmark.symbol)

    # ------------------------------------------------------------------
    def past_events(
        self, archetype_id: str, before: date | None = None, exclude_event_id: str | None = None
    ) -> list[DetectedEvent]:
        out = [
            e
            for e in self.history
            if e.archetype_id == archetype_id
            and (before is None or e.event_date < before)
            and e.event_id != exclude_event_id
        ]
        return sorted(out, key=lambda e: e.event_date)

    # ------------------------------------------------------------------
    def prior_direction(self, archetype_id: str, target: str) -> int:
        """The direction encoded in the transmission map for this pair (0 if none)."""
        try:
            arch = self.kb.archetype(archetype_id)
        except KeyError:
            return 0
        for imp in arch.impacts:
            if imp.target == target:
                return int(imp.direction)
        return 0

    def summarise(
        self,
        archetype_id: str,
        target: str,
        window: str,
        expected_direction: int | None = None,
        before: date | None = None,
        exclude_event_id: str | None = None,
        max_analogs: int = 40,
    ) -> AnalogSummary | None:
        """Run an event study on every past occurrence and aggregate the results.

        `expected_direction` defaults to the direction encoded in the transmission
        map, so the reported hit rate always scores the map's actual claim rather
        than a caller-supplied guess.
        """
        resolved = self.kb.resolve_target(target)
        if resolved is None:
            raise KeyError(f"unknown target '{target}'")
        if expected_direction is None:
            expected_direction = self.prior_direction(archetype_id, target)
        events = self.past_events(archetype_id, before=before, exclude_event_id=exclude_event_id)
        events = events[-max_analogs:]
        if not events:
            return None

        analogs: list[AnalogEvent] = []
        for ev in events:
            try:
                if resolved["kind"] == "basket":
                    res = self.study.run_basket(resolved["symbols"], ev.event_date, window)
                    car = res["caar_bps"]
                else:
                    res = self.study.run(resolved["symbols"][0], ev.event_date, window)
                    car = res["cumulative_abnormal_return_bps"]
            except (InsufficientData, KeyError):
                continue
            analogs.append(
                AnalogEvent(
                    event_id=ev.event_id,
                    event_date=ev.event_date,
                    headline=ev.headline,
                    similarity=round(float(ev.match_score), 3),
                    car_bps=round(float(car), 1),
                )
            )

        if not analogs:
            return None

        cars = np.array([a.car_bps for a in analogs])
        n = len(cars)
        mean = float(cars.mean())
        sd = float(cars.std(ddof=1)) if n > 1 else 0.0
        se = sd / np.sqrt(n) if n > 1 and sd > 0 else 0.0
        t_stat = mean / se if se > 0 else 0.0
        p_value = float(2 * (1 - stats.t.cdf(abs(t_stat), df=max(n - 1, 1)))) if n > 1 else 1.0

        if expected_direction > 0:
            hits = float((cars > 0).mean())
        elif expected_direction < 0:
            hits = float((cars < 0).mean())
        else:
            # for two-sided priors, "hit" = a material move in either direction
            hits = float((np.abs(cars) > 50).mean())

        return AnalogSummary(
            archetype_id=archetype_id,
            target=target,
            window=window,
            sample_size=n,
            mean_car_bps=round(mean, 1),
            median_car_bps=round(float(np.median(cars)), 1),
            stdev_bps=round(sd, 1),
            hit_rate=round(hits, 3),
            p5_bps=round(float(np.percentile(cars, 5)), 1),
            p95_bps=round(float(np.percentile(cars, 95)), 1),
            t_stat=round(t_stat, 3),
            p_value=round(p_value, 4),
            analogs=sorted(analogs, key=lambda a: a.event_date, reverse=True),
        )

    # ------------------------------------------------------------------
    def calibration_report(self, window: str = "T+1..T+5") -> list[dict]:
        """Score every prior in the transmission map against realised history.

        This is the honesty layer. It answers: which of our encoded beliefs are
        actually supported by the data, and which are folklore? Rules that fail
        calibration should be demoted or removed from the map, not defended.
        """
        rows: list[dict] = []
        for arch in self.kb.archetypes.values():
            for imp in arch.impacts:
                summary = self.summarise(
                    arch.id, imp.target, window, expected_direction=imp.direction
                )
                if summary is None:
                    rows.append(
                        {
                            "archetype": arch.id,
                            "target": imp.target,
                            "status": "no_data",
                            "prior_direction": imp.direction,
                            "sample_size": 0,
                        }
                    )
                    continue
                lo, hi = imp.magnitude_prior_bps
                in_range = lo <= summary.median_car_bps <= hi
                sign_ok = (
                    imp.direction == 0
                    or (imp.direction > 0 and summary.median_car_bps > 0)
                    or (imp.direction < 0 and summary.median_car_bps < 0)
                )
                if summary.sample_size < arch.detection.min_sample:
                    status = "underpowered"
                elif sign_ok and in_range:
                    status = "confirmed"
                elif sign_ok:
                    status = "sign_ok_magnitude_off"
                else:
                    status = "contradicted"
                rows.append(
                    {
                        "archetype": arch.id,
                        "target": imp.target,
                        "status": status,
                        "prior_direction": imp.direction,
                        "prior_range_bps": list(imp.magnitude_prior_bps),
                        "realised_median_bps": summary.median_car_bps,
                        "hit_rate": summary.hit_rate,
                        "sample_size": summary.sample_size,
                        "p_value": summary.p_value,
                        "confidence": imp.confidence,
                    }
                )
        return rows


__all__ = ["AnalogEngine"]

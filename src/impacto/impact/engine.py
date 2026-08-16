"""Impact engine: detected event -> ranked sector/basket impact map.

The score is deliberately simple and fully inspectable. A user should be able to
reconstruct any number by hand from the components. An opaque learned score would
rank better on a benchmark and be worthless in a compliance review or an argument
with a portfolio manager.

    score = 100 * direction
          * confidence_weight
          * surprise_weight
          * evidence_weight

where evidence_weight blends the encoded prior with the realised historical hit
rate once enough analogs exist (shrinkage toward the prior at small N).
"""
from __future__ import annotations

from ..eventstudy.analogs import AnalogEngine
from ..knowledge import KnowledgeBase
from ..models import DetectedEvent, ImpactScore

CONFIDENCE_WEIGHT = {"high": 1.0, "medium": 0.7, "low": 0.4}
SHRINKAGE_N = 8  # sample size at which history and prior are weighted 50/50


class ImpactEngine:
    def __init__(self, kb: KnowledgeBase, analogs: AnalogEngine | None = None) -> None:
        self.kb = kb
        self.analogs = analogs

    # ------------------------------------------------------------------
    @staticmethod
    def _surprise_weight(event: DetectedEvent) -> float:
        """Bigger surprises get bigger scores, with saturation.

        A 3-sigma surprise is not 3x a 1-sigma surprise in price impact; the
        relationship is concave. Cap at 1.5x.
        """
        if event.surprise_magnitude is None:
            return 1.0
        m = abs(float(event.surprise_magnitude))
        return float(min(1.5, 0.6 + 0.4 * (m ** 0.5)))

    @staticmethod
    def _evidence_weight(prior_conf: str, hit_rate: float | None, n: int) -> float:
        base = CONFIDENCE_WEIGHT[prior_conf]
        if hit_rate is None or n == 0:
            return base
        w = n / (n + SHRINKAGE_N)
        # hit rate of 0.5 is uninformative -> maps to 1.0 multiplier
        empirical = 0.4 + 1.2 * hit_rate
        return float(base * ((1 - w) * 1.0 + w * empirical))

    # ------------------------------------------------------------------
    def score_event(
        self,
        event: DetectedEvent,
        window: str | None = None,
        with_history: bool = True,
    ) -> list[ImpactScore]:
        arch = self.kb.archetype(event.archetype_id)
        sw = self._surprise_weight(event)
        out: list[ImpactScore] = []

        for imp in arch.impacts:
            resolved = self.kb.resolve_target(imp.target)
            assert resolved is not None  # guaranteed by KnowledgeBase.validate()

            hit_rate = median_car = None
            n = 0
            if with_history and self.analogs is not None:
                summary = self.analogs.summarise(
                    arch.id,
                    imp.target,
                    window or imp.horizon,
                    expected_direction=imp.direction,
                    before=event.event_date,
                    exclude_event_id=event.event_id,
                )
                if summary is not None:
                    hit_rate = summary.hit_rate
                    median_car = summary.median_car_bps
                    n = summary.sample_size

            ew = self._evidence_weight(imp.confidence, hit_rate, n)
            magnitude = 100.0 * ew * sw
            score = round(imp.direction * magnitude, 1) if imp.direction != 0 else 0.0

            out.append(
                ImpactScore(
                    target=imp.target,
                    target_kind=resolved["kind"],
                    direction=imp.direction,
                    score=score,
                    magnitude_prior_bps=imp.magnitude_prior_bps,
                    horizon=imp.horizon,
                    confidence=imp.confidence,
                    channels=imp.channels,
                    rationale=" ".join(imp.rationale.split()),
                    historical_hit_rate=hit_rate,
                    historical_median_car_bps=median_car,
                    sample_size=n,
                )
            )

        # rank by absolute conviction, but keep ambiguous (direction 0) calls
        # visible near the top when confidence is not low — they are the ones a
        # user is most likely to get wrong on their own.
        def sort_key(s: ImpactScore) -> tuple[float, float]:
            ambiguity_bonus = 20.0 if s.direction == 0 and s.confidence != "low" else 0.0
            return (-(abs(s.score) + ambiguity_bonus), s.target)

        return sorted(out, key=sort_key)

    # ------------------------------------------------------------------
    def portfolio_exposure(
        self, event: DetectedEvent, holdings: dict[str, float]
    ) -> dict:
        """Map an event onto a user's holdings without giving advice.

        Output is exposure attribution only: 'X% of your portfolio sits in
        sectors this archetype has historically moved'. It deliberately does not
        recommend an action. See COMPLIANCE.md on the information/advice line.
        """
        scores = {s.target: s for s in self.score_event(event)}
        total = sum(holdings.values()) or 1.0
        rows = []
        for symbol, weight in holdings.items():
            for target, s in scores.items():
                resolved = self.kb.resolve_target(target)
                members = set(resolved.get("symbols", [])) | set(resolved.get("proxies", []) or [])
                if symbol in members:
                    rows.append(
                        {
                            "symbol": symbol,
                            "weight_pct": round(100 * weight / total, 2),
                            "target": target,
                            "direction": s.direction,
                            "confidence": s.confidence,
                            "channels": s.channels,
                        }
                    )
                    break
        exposed = sum(r["weight_pct"] for r in rows)
        return {
            "event_id": event.event_id,
            "archetype_id": event.archetype_id,
            "mapped_weight_pct": round(exposed, 2),
            "unmapped_weight_pct": round(100 - exposed, 2),
            "rows": sorted(rows, key=lambda r: -r["weight_pct"]),
        }


__all__ = ["ImpactEngine", "CONFIDENCE_WEIGHT"]

"""Alert generation.

Design principle: alert on the SURPRISING, not the merely loud. An alert whose
historical analog distribution is indistinguishable from noise is worse than no
alert — it trains the user to ignore the channel. So severity is driven by
statistical evidence, not headline prominence.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from ..explain.guardrails import DISCLAIMER
from ..impact.engine import ImpactEngine
from ..knowledge import KnowledgeBase
from ..models import Alert, DetectedEvent, ImpactScore

HIGH_SCORE = 60.0
WATCH_SCORE = 30.0
MIN_SAMPLE_FOR_HIGH = 6


class AlertEngine:
    def __init__(self, kb: KnowledgeBase, impact: ImpactEngine) -> None:
        self.kb = kb
        self.impact = impact

    @staticmethod
    def _severity(scores: list[ImpactScore]) -> str:
        if not scores:
            return "info"
        top = scores[0]
        strong = abs(top.score) >= HIGH_SCORE
        evidenced = top.sample_size >= MIN_SAMPLE_FOR_HIGH and (top.historical_hit_rate or 0) >= 0.65
        if strong and evidenced:
            return "high"
        if abs(top.score) >= WATCH_SCORE:
            return "watch"
        return "info"

    def build(self, event: DetectedEvent, max_targets: int = 4) -> Alert:
        arch = self.kb.archetype(event.archetype_id)
        scores = self.impact.score_event(event)
        severity = self._severity(scores)
        top = scores[:max_targets]

        lines = [f"{arch.label} detected — {event.headline}", ""]
        lines.append("Sectors this archetype has historically moved:")
        for s in top:
            arrow = {1: "up", -1: "down", 0: "two-sided"}[s.direction]
            name = self.kb.resolve_target(s.target)["name"]
            hist = (
                f"historically {s.historical_median_car_bps:+.0f}bps median over "
                f"{s.sample_size} past occurrences (hit rate {s.historical_hit_rate:.0%})"
                if s.sample_size
                else "no historical sample yet"
            )
            chans = ", ".join(self.kb.channel(c).name for c in s.channels)
            lines.append(f"  - {name}: {arrow}, {s.confidence} confidence — {hist}")
            lines.append(f"    channel: {chans}")
            lines.append(f"    why: {s.rationale}")
        if severity == "info":
            lines.append("")
            lines.append(
                "Flagged as low-signal: the historical distribution for this "
                "archetype is not statistically distinguishable from noise."
            )

        alert_id = hashlib.sha1(
            f"{event.event_id}|{severity}".encode()
        ).hexdigest()[:12]
        return Alert(
            alert_id=alert_id,
            created_at=datetime.now(UTC),
            severity=severity,  # type: ignore[arg-type]
            archetype_id=event.archetype_id,
            headline=event.headline,
            targets=[s.target for s in top],
            body="\n".join(lines),
            disclaimer=DISCLAIMER,
        )

    def build_many(self, events: list[DetectedEvent], min_severity: str = "info") -> list[Alert]:
        order = {"info": 0, "watch": 1, "high": 2}
        floor = order[min_severity]
        alerts = [self.build(e) for e in events]
        return [a for a in alerts if order[a.severity] >= floor]


__all__ = ["AlertEngine", "HIGH_SCORE", "WATCH_SCORE"]

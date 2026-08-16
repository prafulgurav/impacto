"""Daily digest: 'here is what happened globally overnight and where it lands.'

Format follows the newsroom inverted pyramid — the single most consequential
read first, then the evidence, then the watchlist. Users abandon digests that
bury the lede.
"""
from __future__ import annotations

from datetime import UTC, date, datetime

from ..explain.guardrails import DISCLAIMER
from ..impact.engine import ImpactEngine
from ..knowledge import KnowledgeBase
from ..models import DetectedEvent, Digest, DigestSection


class DigestBuilder:
    def __init__(self, kb: KnowledgeBase, impact: ImpactEngine) -> None:
        self.kb = kb
        self.impact = impact

    def build(self, events: list[DetectedEvent], digest_date: date | None = None) -> Digest:
        digest_date = digest_date or date.today()
        events = sorted(events, key=lambda e: e.event_date, reverse=True)

        if not events:
            return Digest(
                digest_date=digest_date,
                generated_at=datetime.now(UTC),
                headline_summary="No global events matching the tracked archetypes were detected.",
                sections=[],
                events=[],
                disclaimer=DISCLAIMER,
            )

        scored = [(e, self.impact.score_event(e)) for e in events]
        scored.sort(key=lambda pair: -max((abs(s.score) for s in pair[1]), default=0.0))
        lead_event, lead_scores = scored[0]
        lead_arch = self.kb.archetype(lead_event.archetype_id)
        top = lead_scores[0] if lead_scores else None

        if top is not None:
            lead_name = self.kb.resolve_target(top.target)["name"]
            headline = (
                f"{lead_arch.label}. The sector with the strongest historical "
                f"linkage is {lead_name} via the "
                f"{self.kb.channel(top.channels[0]).name.lower()} channel."
            )
        else:
            headline = lead_arch.label

        sections: list[DigestSection] = []

        # 1. What happened
        sections.append(
            DigestSection(
                title="What happened",
                bullets=[
                    f"{self.kb.archetype(e.archetype_id).label}: {e.headline}"
                    for e, _ in scored[:6]
                ],
            )
        )

        # 2. Where it lands
        landing: list[str] = []
        seen: set[str] = set()
        for _, ss in scored:
            for s in ss[:3]:
                if s.target in seen:
                    continue
                seen.add(s.target)
                name = self.kb.resolve_target(s.target)["name"]
                arrow = {1: "positive", -1: "negative", 0: "two-sided"}[s.direction]
                hist = (
                    f" — median {s.historical_median_car_bps:+.0f}bps across "
                    f"{s.sample_size} past occurrences"
                    if s.sample_size
                    else ""
                )
                landing.append(
                    f"{name}: historical linkage {arrow} ({s.confidence} confidence){hist}. "
                    f"Channel: {', '.join(self.kb.channel(c).name for c in s.channels)}."
                )
        sections.append(DigestSection(title="Where it historically lands", bullets=landing[:8]))

        # 3. What would change the read
        ambiguous = [
            s
            for _, ss in scored
            for s in ss
            if s.direction == 0 or s.confidence == "low"
        ]
        if ambiguous:
            sections.append(
                DigestSection(
                    title="Where the read is genuinely uncertain",
                    bullets=[
                        f"{self.kb.resolve_target(s.target)['name']}: {s.rationale}"
                        for s in ambiguous[:5]
                    ],
                )
            )

        # 4. Calendar
        sections.append(
            DigestSection(
                title="Method note",
                bullets=[
                    "Every linkage above cites an economic transmission channel defined in "
                    "knowledge/channels.yaml — none are derived from headline sentiment alone.",
                    "Historical figures are cumulative abnormal returns from a market-model "
                    "event study against NIFTY 50, not raw returns.",
                    "Distributions describe the past. They are not forecasts and no "
                    "action is recommended.",
                ],
            )
        )

        return Digest(
            digest_date=digest_date,
            generated_at=datetime.now(UTC),
            headline_summary=headline,
            sections=sections,
            events=[e for e, _ in scored],
            disclaimer=DISCLAIMER,
        )

    def to_markdown(self, digest: Digest) -> str:
        out = [
            f"# Impacto — {digest.digest_date.isoformat()}",
            "",
            f"**{digest.headline_summary}**",
            "",
        ]
        for sec in digest.sections:
            out.append(f"## {sec.title}")
            out.append("")
            out.extend(f"- {b}" for b in sec.bullets)
            out.append("")
        out.append("---")
        out.append(f"_{digest.disclaimer}_")
        return "\n".join(out)


__all__ = ["DigestBuilder"]

"""Grounded explainer: 'why did IT stocks fall today?'

Architecture is retrieval-first and generation-last, deliberately:

  1. RETRIEVE  — find candidate archetypes active around the date, pull their
                 transmission-map entries and realised event-study statistics.
  2. COMPOSE   — build a fully-cited, deterministic answer from those facts.
                 This answer is complete and shippable on its own.
  3. NARRATE   — (optional) an LLM rewrites the composed answer into fluent prose.
                 It is given ONLY the retrieved facts, is forbidden from adding
                 new numbers, and its output passes through the guardrail filter.

If the LLM is unavailable, misconfigured, or its output fails compliance, the
system falls back to the step-2 answer. It never degrades to an ungrounded one.
That inversion — templates as the product, LLM as a polish layer — is what makes
the output auditable enough to defend in a SEBI review.
"""
from __future__ import annotations

from datetime import date, timedelta

from ..eventstudy.analogs import AnalogEngine
from ..impact.engine import ImpactEngine
from ..knowledge import KnowledgeBase
from ..llm import SYSTEM_PROMPT, LLMError, LLMProvider, get_llm
from ..models import Citation, DetectedEvent, Explanation
from .guardrails import DISCLAIMER, check_output


class Explainer:
    def __init__(
        self,
        kb: KnowledgeBase,
        impact: ImpactEngine,
        analogs: AnalogEngine,
        event_history: list[DetectedEvent] | None = None,
        llm: LLMProvider | None = None,
    ) -> None:
        self.kb = kb
        self.impact = impact
        self.analogs = analogs
        self.history = event_history or analogs.history
        self._llm = llm

    @property
    def llm(self) -> LLMProvider:
        # Resolved lazily so a test can construct an Explainer without touching env.
        if self._llm is None:
            self._llm = get_llm()
        return self._llm

    # ------------------------------------------------------------- retrieve
    def _events_near(self, as_of: date, lookback_days: int = 5) -> list[DetectedEvent]:
        lo = as_of - timedelta(days=lookback_days)
        return [e for e in self.history if lo <= e.event_date <= as_of]

    def _resolve_target_from_question(self, question: str) -> str | None:
        q = question.lower()
        # longest name first so 'nifty psu bank' wins over 'nifty bank'
        candidates: list[tuple[str, str]] = []
        for tid in list(self.kb.sectors) + list(self.kb.baskets) + [self.kb.benchmark.id]:
            resolved = self.kb.resolve_target(tid)
            candidates.append((tid, resolved["name"].lower()))
            candidates.append((tid, tid.replace("_", " ").lower()))
        candidates.sort(key=lambda c: -len(c[1]))
        for tid, name in candidates:
            if name in q:
                return tid
        aliases = {
            "it stocks": "NIFTY_IT", "tech stocks": "NIFTY_IT", "software": "NIFTY_IT",
            "banks": "NIFTY_BANK", "banking": "NIFTY_BANK", "lenders": "NIFTY_BANK",
            "oil": "NIFTY_ENERGY", "energy": "NIFTY_ENERGY", "refiners": "OMC",
            "pharma": "NIFTY_PHARMA", "metals": "NIFTY_METAL", "steel": "NIFTY_METAL",
            "auto": "NIFTY_AUTO", "cars": "NIFTY_AUTO", "realty": "NIFTY_REALTY",
            "real estate": "NIFTY_REALTY", "airlines": "AVIATION", "aviation": "AVIATION",
            "market": "NIFTY_50", "nifty": "NIFTY_50", "sensex": "NIFTY_50",
        }
        for alias, tid in sorted(aliases.items(), key=lambda kv: -len(kv[0])):
            if alias in q:
                return tid
        return None

    # -------------------------------------------------------------- compose
    def _compose(
        self, question: str, as_of: date, target: str | None
    ) -> tuple[str, list[Citation]]:
        citations: list[Citation] = []
        events = self._events_near(as_of)
        if not events:
            return (
                f"No global event matching a tracked archetype was detected in the five "
                f"sessions to {as_of.isoformat()}. The move you are asking about is not "
                f"explained by anything in the global-event corpus — it may be domestic, "
                f"stock-specific, or flow-driven.",
                citations,
            )

        target = target or self._resolve_target_from_question(question)
        paras: list[str] = []

        relevant: list[tuple[DetectedEvent, object]] = []
        for ev in events:
            scores = self.impact.score_event(ev)
            if target:
                match = [s for s in scores if s.target == target]
                if not match:
                    continue
                relevant.append((ev, match[0]))
            else:
                relevant.append((ev, scores[0]))

        if not relevant:
            names = ", ".join(self.kb.archetype(e.archetype_id).label for e in events[:3])
            tname = self.kb.resolve_target(target)["name"] if target else "that target"
            return (
                f"Global events were detected in the window to {as_of.isoformat()} "
                f"({names}), but the transmission map does not encode a linkage from any "
                f"of them to {tname}. On the evidence available, the move is not "
                f"attributable to these global events.",
                citations,
            )

        relevant.sort(key=lambda pair: -abs(getattr(pair[1], "score", 0.0)))

        for ev, score in relevant[:3]:
            arch = self.kb.archetype(ev.archetype_id)
            tname = self.kb.resolve_target(score.target)["name"]
            chan_names = [self.kb.channel(c) for c in score.channels]
            chan_txt = "; ".join(f"{c.name} — {' '.join(c.description.split())}" for c in chan_names)

            summary = self.analogs.summarise(
                arch.id, score.target, score.horizon,
                expected_direction=score.direction, before=as_of,
            )

            para = [
                f"{arch.label} was detected on {ev.event_date.isoformat()} ({ev.headline}).",
                f"The transmission map links this archetype to {tname} through: {chan_txt}",
                f"Encoded reasoning: {score.rationale}",
            ]
            if summary and summary.sample_size:
                direction_word = {1: "positive", -1: "negative", 0: "two-sided"}[score.direction]
                para.append(
                    f"Historically, across {summary.sample_size} past occurrences of this "
                    f"archetype, {tname} recorded a median cumulative abnormal return of "
                    f"{summary.median_car_bps:+.0f} bps over the {summary.window} window "
                    f"(mean {summary.mean_car_bps:+.0f} bps, 5th-95th percentile "
                    f"{summary.p5_bps:+.0f} to {summary.p95_bps:+.0f} bps, "
                    f"p = {summary.p_value:.3f}). The prior encoded in the map is "
                    f"{direction_word} with {score.confidence} confidence, and the realised "
                    f"hit rate was {summary.hit_rate:.0%}."
                )
                if summary.p_value > 0.10:
                    para.append(
                        "That distribution is not statistically distinguishable from zero, "
                        "so this linkage should be treated as weak evidence."
                    )
                citations.append(
                    Citation(
                        label=f"Event study: {arch.id} -> {score.target}",
                        kind="analog",
                        detail=(
                            f"n={summary.sample_size}, median={summary.median_car_bps:+.0f}bps, "
                            f"window={summary.window}, p={summary.p_value:.3f}"
                        ),
                    )
                )
            else:
                para.append(
                    "There is no usable historical sample for this archetype-target pair yet, "
                    "so the linkage rests on the economic mechanism alone."
                )
            if score.direction == 0:
                para.append(
                    "Note this linkage is explicitly two-sided in the map: the mechanism can "
                    "cut either way and the sign depends on the specific cause of the event."
                )
            paras.append(" ".join(para))
            citations.append(
                Citation(label=f"Event: {ev.event_id}", kind="event", detail=ev.headline)
            )
            citations.append(
                Citation(
                    label=f"Transmission rule: {arch.id} -> {score.target}",
                    kind="transmission_map",
                    detail=f"channels={','.join(score.channels)}; confidence={score.confidence}",
                )
            )

        return "\n\n".join(paras), citations

    # -------------------------------------------------------------- narrate
    @staticmethod
    def _user_prompt(question: str, facts: str) -> str:
        return f"QUESTION:\n{question}\n\nRETRIEVED FACTS:\n{facts}"

    def _narrate(self, question: str, facts: str) -> str | None:
        """Ask the configured provider to rewrite the composed answer.

        Returns None on any failure. The caller already holds a complete, compliant
        answer, so a provider outage is a style regression and nothing more.
        """
        try:
            text = self.llm.complete(SYSTEM_PROMPT, self._user_prompt(question, facts))
        except LLMError:
            return None
        except Exception:
            # A provider SDK can raise anything. Narration is never worth an outage.
            return None
        return text.strip() or None

    def compose(
        self, question: str, as_of: date | None = None, target: str | None = None
    ) -> tuple[str, list[Citation]]:
        """The deterministic, fully-cited answer. Public because SSE emits it first."""
        return self._compose(question, as_of or date.today(), target)

    def narrate_stream(self, question: str, facts: str):
        """Yield narration tokens. Raises LLMError so the SSE layer can fall back."""
        yield from self.llm.stream(SYSTEM_PROMPT, self._user_prompt(question, facts))

    # ------------------------------------------------------------------ api
    def finalise(
        self,
        question: str,
        facts: str,
        citations: list[Citation],
        narrated: str | None,
    ) -> Explanation:
        """Apply the guardrail and build the response.

        Shared by `explain()` and the SSE endpoint so both paths enforce compliance
        identically — a second implementation is a second thing to get wrong.
        """
        answer, used_llm = facts, False
        if narrated:
            if check_output(narrated, strict=True).passed:
                answer, used_llm = narrated, True
            # Non-compliant narration falls back to the grounded composition rather
            # than shipping a redacted mess.

        final_check = check_output(answer, strict=False)
        return Explanation(
            question=question,
            answer=answer,
            citations=citations,
            compliance_flags=final_check.flags,
            used_llm=used_llm,
            disclaimer=DISCLAIMER,
        )

    def explain(
        self, question: str, as_of: date | None = None, target: str | None = None
    ) -> Explanation:
        as_of = as_of or date.today()
        facts, citations = self._compose(question, as_of, target)
        return self.finalise(question, facts, citations, self._narrate(question, facts))


__all__ = ["Explainer", "SYSTEM_PROMPT"]

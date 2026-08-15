"""Composition root. One place that wires the object graph together."""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

from .alerts.digest import DigestBuilder
from .alerts.rules import AlertEngine
from .config import get_settings
from .eventstudy.analogs import AnalogEngine
from .eventstudy.car import EventStudy
from .explain.explainer import Explainer
from .impact.engine import ImpactEngine
from .ingest.classifier import EventClassifier
from .ingest.sources import FixtureNewsSource, GDELTSource, RSSSource, load_event_history
from .knowledge import KnowledgeBase
from .market.provider import get_provider
from .models import DetectedEvent


class Impacto:
    """Facade over the whole pipeline. The API and CLI both talk to this."""

    def __init__(self, provider_name: str | None = None) -> None:
        self.settings = get_settings()
        self.kb = KnowledgeBase()
        self.provider = get_provider(provider_name)
        self.history: list[DetectedEvent] = load_event_history()
        self.analogs = AnalogEngine(self.kb, self.provider, self.history)
        self.impact = ImpactEngine(self.kb, self.analogs)
        self.study = EventStudy(self.provider, benchmark_symbol=self.kb.benchmark.symbol)
        self.classifier = EventClassifier(self.kb)
        self.alerts = AlertEngine(self.kb, self.impact)
        self.digests = DigestBuilder(self.kb, self.impact)
        self.explainer = Explainer(self.kb, self.impact, self.analogs, self.history)

    # ------------------------------------------------------------------
    def news_sources(self) -> list:
        if self.settings.market_provider == "fixture":
            return [FixtureNewsSource()]
        sources: list = [RSSSource()]
        if self.settings.gdelt_enabled:
            sources.append(GDELTSource())
        return sources

    def detect(self, since: date, until: date | None = None) -> list[DetectedEvent]:
        items = []
        for src in self.news_sources():
            items.extend(src.fetch(since, until))
        return self.classifier.to_events(items)

    def events_on(self, day: date, lookback_days: int = 1) -> list[DetectedEvent]:
        lo = day - timedelta(days=lookback_days)
        return [e for e in self.history if lo <= e.event_date <= day]

    def latest_event_date(self) -> date:
        return max((e.event_date for e in self.history), default=date.today())


@lru_cache(maxsize=1)
def get_service() -> Impacto:
    return Impacto()


__all__ = ["Impacto", "get_service"]

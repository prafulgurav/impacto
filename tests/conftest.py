from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from impacto.eventstudy.analogs import AnalogEngine  # noqa: E402
from impacto.eventstudy.car import EventStudy  # noqa: E402
from impacto.impact.engine import ImpactEngine  # noqa: E402
from impacto.ingest.classifier import EventClassifier  # noqa: E402
from impacto.ingest.sources import load_event_history  # noqa: E402
from impacto.knowledge import KnowledgeBase  # noqa: E402
from impacto.market.provider import FixtureProvider  # noqa: E402
from impacto.service import Impacto  # noqa: E402


@pytest.fixture(scope="session")
def kb() -> KnowledgeBase:
    return KnowledgeBase(ROOT / "knowledge")


@pytest.fixture(scope="session")
def provider() -> FixtureProvider:
    return FixtureProvider(ROOT / "data" / "fixtures")


@pytest.fixture(scope="session")
def raw_events() -> list[dict]:
    import json

    return json.loads((ROOT / "data" / "fixtures" / "events.json").read_text())


@pytest.fixture(scope="session")
def history():
    return load_event_history(ROOT / "data" / "fixtures")


@pytest.fixture(scope="session")
def study(provider, kb) -> EventStudy:
    return EventStudy(provider, benchmark_symbol=kb.benchmark.symbol)


@pytest.fixture(scope="session")
def analogs(kb, provider, history) -> AnalogEngine:
    return AnalogEngine(kb, provider, history)


@pytest.fixture(scope="session")
def impact(kb, analogs) -> ImpactEngine:
    return ImpactEngine(kb, analogs)


@pytest.fixture(scope="session")
def classifier(kb) -> EventClassifier:
    return EventClassifier(kb)


@pytest.fixture(scope="session")
def service() -> Impacto:
    return Impacto(provider_name="fixture")

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from impacto.db import Repositories, create_all  # noqa: E402
from impacto.db.session import build_engine  # noqa: E402
from impacto.db.types import generate_encryption_key  # noqa: E402
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


# ------------------------------------------------------------------ database
@pytest.fixture(scope="session", autouse=True)
def _encryption_key():
    """Holdings columns fail closed without a key, so every DB test needs one.

    Generated per session rather than hardcoded: a fixed test key in the repo is the
    kind of thing that ends up in a deployment.
    """
    import os

    os.environ.setdefault("IMPACTO_HOLDINGS_ENCRYPTION_KEY", generate_encryption_key())


@pytest.fixture()
def engine():
    """A fresh in-memory database per test.

    Hermetic and fast; the migration path itself is covered separately in
    test_migrations.py, which runs `alembic upgrade head` against a real file.
    """
    eng = build_engine("sqlite://")
    create_all(eng)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture()
def db(engine):
    """A `Repositories` bundle bound to one transaction, rolled back after the test."""
    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    session = factory()
    try:
        yield Repositories(session)
        session.rollback()
    finally:
        session.close()


@pytest.fixture()
def user(db):
    u = db.users.upsert_by_email("Reader@Example.COM")
    db.flush()
    return u


# ----------------------------------------------------------------------- api
WEB_ORIGIN = "https://impacto.example"
TEST_JWT_SECRET = "test-secret-value-not-for-production"


@pytest.fixture()
def app(engine, monkeypatch):
    """The real application, wired to this test's database.

    `repos_dep` is overridden rather than pointing IMPACTO_DATABASE_URL at a
    temp file, so the app and the test share one in-memory database and a test
    can assert on rows the request just wrote.
    """
    from sqlalchemy.orm import sessionmaker

    from impacto.api import deps
    from impacto.api.app import create_app
    from impacto.api.cache import reset_cache
    from impacto.config import reset_settings_cache

    monkeypatch.setenv("IMPACTO_JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setenv("IMPACTO_WEB_ORIGIN", WEB_ORIGIN)
    monkeypatch.setenv("IMPACTO_COOKIE_SECURE", "false")
    reset_settings_cache()
    reset_cache()

    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def override_repos():
        session = factory()
        try:
            yield Repositories(session)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    application = create_app()
    application.dependency_overrides[deps.repos_dep] = override_repos
    try:
        yield application
    finally:
        reset_settings_cache()
        reset_cache()


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient

    return TestClient(app)

"""The migration path itself.

`create_all()` is what the unit tests use, and it can drift from the migrations
without anything noticing. This runs `alembic upgrade head` against a real empty
database and asserts the result matches the models — which is the acceptance
criterion for Phase 1 and the thing that breaks a production deploy if it rots.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import inspect

from impacto.db.models import Base
from impacto.db.session import build_engine

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def upgraded_db(tmp_path, monkeypatch):
    """A file database taken from empty to head by the real alembic CLI."""
    db_path = tmp_path / "migrated.db"
    url = f"sqlite:///{db_path}"
    env = {
        **dict(**__import__("os").environ),
        "IMPACTO_DATABASE_URL": url,
        "PYTHONPATH": str(ROOT / "src"),
    }
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    engine = build_engine(url)
    try:
        yield engine
    finally:
        engine.dispose()


def test_upgrade_head_runs_clean_on_an_empty_database(upgraded_db):
    tables = set(inspect(upgraded_db).get_table_names())
    expected = set(Base.metadata.tables) | {"alembic_version"}
    assert expected <= tables, f"missing: {expected - tables}"


def test_every_table_from_the_brief_exists(upgraded_db):
    tables = set(inspect(upgraded_db).get_table_names())
    assert {
        "users",
        "sessions",
        "watchlist_archetypes",
        "holdings",
        "push_subscriptions",
        "analog_summaries",
        "detected_events",
        "daily_digests",
        "calibration_runs",
        "audit_log",
    } <= tables


def test_the_indexes_the_brief_names_are_present(upgraded_db):
    """§2.1 lists these three by name because they carry the hot read paths."""
    inspector = inspect(upgraded_db)
    names = {
        table: {i["name"] for i in inspector.get_indexes(table)}
        for table in ("detected_events", "analog_summaries", "audit_log")
    }
    assert "ix_detected_events_date_desc" in names["detected_events"]
    assert "ix_analog_summaries_archetype_target" in names["analog_summaries"]
    assert "ix_audit_log_created_at" in names["audit_log"]


def test_migrated_columns_match_the_models(upgraded_db):
    """Catches a model change that never made it into a migration."""
    inspector = inspect(upgraded_db)
    for name, table in Base.metadata.tables.items():
        migrated = {c["name"] for c in inspector.get_columns(name)}
        declared = {c.name for c in table.columns}
        assert declared == migrated, f"{name}: models={declared} migrated={migrated}"


def test_holdings_columns_are_binary_not_text(upgraded_db):
    """The encrypted columns must survive the migration as blobs."""
    types = {
        c["name"]: str(c["type"]).upper()
        for c in inspect(upgraded_db).get_columns("holdings")
    }
    assert "BLOB" in types["symbol"]
    assert "BLOB" in types["weight"]

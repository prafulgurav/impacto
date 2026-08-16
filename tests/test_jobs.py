"""Scheduled jobs.

These run against the fixture provider and the bundled news corpus, so they are
hermetic — no network, deterministic output, and the same code path the scheduler
executes in production.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from impacto.jobs import (
    build_scheduler,
    digest_subscribers,
    push_targets,
    run_calibration,
    run_digest,
    run_ingest,
    run_precompute,
)

# The full five-window, fifteen-archetype sweep is the Phase 1 acceptance criterion
# and takes real time. It runs once, marked slow. Every other test scopes the sweep
# to two archetypes and one window, which exercises identical code in ~1s.
ONE_WINDOW = ["T+1..T+5"]
SAMPLE_ARCHETYPES = ["US_IMMIGRATION_VISA_TIGHTENING", "US_CPI_UPSIDE_SURPRISE"]


def precompute_sample(service, db, **kwargs):
    kwargs.setdefault("windows", ONE_WINDOW)
    kwargs.setdefault("archetype_ids", SAMPLE_ARCHETYPES)
    kwargs.setdefault("as_of", date.today())
    return run_precompute(service, db, **kwargs)


# ------------------------------------------------------------------ precompute
def test_precompute_fills_summaries_for_every_combination(service, db):
    result = precompute_sample(service, db)
    assert result.ok, result.errors
    assert result.combinations == sum(
        len(service.kb.archetypes[a].impacts) for a in SAMPLE_ARCHETYPES
    )
    assert result.rows_written > 0
    assert db.analogs.count(as_of=date.today()) == result.rows_written


@pytest.mark.slow
def test_full_sweep_covers_every_rule_within_the_time_budget(service, db):
    """Acceptance (§9, Phase 1): a full sweep in under 120 seconds.

    The brief also states ">=300 rows", but that figure came from an estimate of
    ~25 rules per window. The shipped transmission map has 55 rules, so five
    windows yield at most 275 combinations — 300 is arithmetically unreachable
    without adding windows or rules, and padding either to hit a number would be
    gaming the metric.

    So the assertion here is the property the row count was standing in for:
    every rule/window combination produces a row, none silently missing.
    """
    from impacto.config import get_settings

    windows = get_settings().analog_window_list
    assert len(windows) == 5, "the brief specifies five windows"

    rules = sum(len(a.impacts) for a in service.kb.archetypes.values())
    result = run_precompute(service, db, as_of=date.today(), windows=windows)

    assert result.ok, result.errors
    assert result.combinations == rules * len(windows)
    assert result.rows_written + result.skipped_no_data == result.combinations
    assert result.rows_written == db.analogs.count(as_of=date.today())
    assert result.duration_seconds < 120, f"took {result.duration_seconds:.1f}s"


def test_precompute_is_idempotent_within_a_day(service, db):
    today = date.today()
    first = precompute_sample(service, db)
    precompute_sample(service, db)
    assert db.analogs.count(as_of=today) == first.rows_written


def test_precompute_prunes_slices_beyond_the_retention_window(service, db):
    old = date.today() - timedelta(days=30)
    precompute_sample(service, db, as_of=old, keep_days=0)
    result = precompute_sample(service, db, keep_days=7)
    assert result.pruned > 0
    assert db.analogs.count(as_of=old) == 0


def test_precomputed_rows_carry_their_uncertainty(service, db):
    """A median with no n and no p-value is not shippable (non-negotiable #2)."""
    precompute_sample(service, db)
    for row in db.analogs.for_window("T+1..T+5"):
        assert row.sample_size > 0
        assert row.p_value is not None
        assert row.median_car_bps is not None


@pytest.mark.slow
def test_calibration_run_is_recorded_with_a_status_breakdown(service, db):
    assert run_calibration(service, db, windows=ONE_WINDOW) == 1
    run = db.calibration.latest("T+1..T+5")
    assert run is not None
    assert sum(run.summary.values()) == len(run.rows)
    assert set(run.summary) <= {
        "confirmed",
        "sign_ok_magnitude_off",
        "contradicted",
        "underpowered",
        "no_data",
    }


# ---------------------------------------------------------------------- ingest
# In production ingest runs every 30 minutes over a two-day lookback, so it sees a
# handful of events. Pointing it at the entire fixture corpus (393 events) would
# score every one of them and take two minutes — a load the job never actually
# carries. These tests use a realistic recent window instead.
INGEST_DAYS = 21


def ingest_window(service):
    latest = service.latest_event_date()
    return latest - timedelta(days=INGEST_DAYS), latest


def test_ingest_persists_classified_events(service, db):
    since, until = ingest_window(service)
    result = run_ingest(service, db, since=since, until=until)
    assert result.ok, result.errors
    assert result.detected > 0
    assert result.new == result.detected
    assert len(db.events.recent(since, limit=1000)) == result.new


def test_rerunning_ingest_adds_nothing_new(service, db):
    since, until = ingest_window(service)
    first = run_ingest(service, db, since=since, until=until)
    second = run_ingest(service, db, since=since, until=until)
    assert second.new == 0
    assert second.updated == first.detected
    assert len(db.events.recent(since, limit=1000)) == first.new


def test_only_new_events_can_raise_an_alert(service, db):
    """Re-classifying a known event must not notify the same user twice."""
    since, until = ingest_window(service)
    run_ingest(service, db, since=since, until=until, min_severity="info")
    second = run_ingest(service, db, since=since, until=until, min_severity="info")
    assert second.alerts == []


def test_ingest_survives_a_dead_news_source(service, db, monkeypatch):
    monkeypatch.setattr(
        service, "detect", lambda *a, **k: (_ for _ in ()).throw(OSError("feed down"))
    )
    result = run_ingest(service, db)
    assert result.ok is False
    assert result.detected == 0
    assert "feed down" in result.errors[0]


def test_push_fan_out_targets_only_matching_watchlists(service, db, user):
    since, until = ingest_window(service)
    result = run_ingest(service, db, since=since, until=until, min_severity="info")
    assert result.alerts, "fixture corpus should raise at least one alert"

    watched = result.alerts[0].archetype_id
    db.watchlist.replace(user.id, [watched], min_severity="info")
    db.flush()

    targets = push_targets(db, result.alerts)
    assert user.id in targets[result.alerts[0].alert_id]
    for alert in result.alerts:
        if alert.archetype_id != watched:
            assert user.id not in targets[alert.alert_id]


# ---------------------------------------------------------------------- digest
def test_digest_is_built_and_stored(service, db):
    day = service.latest_event_date()
    result = run_digest(service, db, day=day)
    assert result.ok, result.errors
    stored = db.digests.get(day)
    assert stored is not None
    assert stored.payload["digest_date"] == day.isoformat()
    assert stored.payload["disclaimer"]


def test_digest_upsert_replaces_rather_than_duplicates(service, db):
    day = service.latest_event_date()
    run_digest(service, db, day=day)
    run_digest(service, db, day=day)
    assert db.digests.latest().digest_date == day


def test_digest_subscribers_are_deduplicated(service, db, user):
    day = service.latest_event_date()
    run_digest(service, db, day=day)
    digest = service.digests.build(service.events_on(day, 3), digest_date=day)
    archetypes = {e.archetype_id for e in digest.events}
    if not archetypes:
        pytest.skip("no events in the digest window for this fixture date")

    db.watchlist.replace(user.id, sorted(archetypes), min_severity="info")
    db.flush()
    assert digest_subscribers(db, digest) == [user.id]


def test_digest_reports_a_failure_rather_than_raising(service, db, monkeypatch):
    monkeypatch.setattr(
        service.digests,
        "build",
        lambda *a, **k: (_ for _ in ()).throw(ValueError("bad digest")),
    )
    result = run_digest(service, db)
    assert result.ok is False
    assert "bad digest" in result.errors[0]


# ------------------------------------------------------------------- scheduler
def test_scheduler_registers_the_three_jobs_on_ist():
    from apscheduler.schedulers.background import BackgroundScheduler

    sched = build_scheduler(BackgroundScheduler(timezone="Asia/Kolkata"))
    try:
        jobs = {j.id: j for j in sched.get_jobs()}
        assert set(jobs) == {"precompute", "ingest", "digest"}
        assert all(str(j.trigger.timezone) == "Asia/Kolkata" for j in jobs.values())
    finally:
        sched.shutdown(wait=False) if sched.running else None


def test_scheduler_schedules_match_the_brief():
    from apscheduler.schedulers.background import BackgroundScheduler

    sched = build_scheduler(BackgroundScheduler(timezone="Asia/Kolkata"))
    fields = {
        j.id: {f.name: str(f) for f in j.trigger.fields} for j in sched.get_jobs()
    }
    assert fields["precompute"]["hour"] == "2"          # 02:00 IST daily
    assert fields["digest"]["hour"] == "7"              # 07:30 IST
    assert fields["digest"]["minute"] == "30"
    assert fields["digest"]["day_of_week"] == "mon-fri"
    assert fields["ingest"]["hour"] == "6-23"           # market hours
    assert fields["ingest"]["minute"] == "*/30"


def test_scheduler_is_off_unless_explicitly_enabled(monkeypatch):
    """Two API replicas each running the jobs would double-notify every user."""
    from impacto.config import reset_settings_cache
    from impacto.jobs import start_scheduler

    monkeypatch.delenv("IMPACTO_SCHEDULER_ENABLED", raising=False)
    reset_settings_cache()
    try:
        assert start_scheduler() is None
    finally:
        reset_settings_cache()

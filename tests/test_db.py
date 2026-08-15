"""Repository layer.

The two properties worth pinning hardest are the ones a future change could quietly
break without failing anything else: holdings must be unreadable in the database,
and reading them must always leave an audit trail.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from impacto.db.models import AuditLog, Holding
from impacto.db.repositories import MAX_PUSH_FAILURES, hash_token
from impacto.db.types import MissingEncryptionKey
from impacto.models import AnalogEvent, AnalogSummary, DetectedEvent


# ---------------------------------------------------------------------- users
def test_email_is_normalised_so_lookup_is_case_insensitive(db):
    created = db.users.upsert_by_email("Reader@Example.COM")
    assert created.email == "reader@example.com"
    assert db.users.by_email("READER@example.com").id == created.id


def test_upsert_by_email_is_idempotent(db):
    first = db.users.upsert_by_email("a@b.com")
    second = db.users.upsert_by_email("A@B.com", locale="hi-IN")
    assert first.id == second.id
    assert second.locale == "hi-IN"


def test_deleting_a_user_cascades_to_their_data(db, user):
    db.watchlist.replace(user.id, ["US_IMMIGRATION_VISA_TIGHTENING"])
    db.holdings.replace(user.id, {"TCS": 0.5})
    db.push.subscribe(user.id, "https://push/1", "p", "a")
    db.flush()

    assert db.users.delete(user.id) is True
    db.flush()
    assert db.watchlist.list(user.id) == []
    assert db.push.list(user.id) == []
    assert db.session.scalars(select(Holding).where(Holding.user_id == user.id)).all() == []


# ------------------------------------------------------------------- sessions
def test_refresh_token_is_stored_hashed_never_raw(db, user):
    db.auth_sessions.create(user.id, "super-secret-token", ttl_days=30)
    db.flush()
    stored = db.session.execute(text("SELECT refresh_token_hash FROM sessions")).scalar()
    assert stored == hash_token("super-secret-token")
    assert "super-secret-token" not in stored


def test_session_lookup_round_trips_and_revokes(db, user):
    db.auth_sessions.create(user.id, "tok", ttl_days=30)
    db.flush()
    assert db.auth_sessions.by_token("tok") is not None

    assert db.auth_sessions.revoke("tok") is True
    db.flush()
    assert db.auth_sessions.by_token("tok") is None


def test_expired_session_is_not_returned(db, user):
    db.auth_sessions.create(user.id, "old", ttl_days=-1)
    db.flush()
    assert db.auth_sessions.by_token("old") is None


def test_revoke_all_ends_every_live_session(db, user):
    for token in ("a", "b", "c"):
        db.auth_sessions.create(user.id, token, ttl_days=30)
    db.flush()
    assert db.auth_sessions.revoke_all(user.id) == 3
    db.flush()
    assert all(db.auth_sessions.by_token(t) is None for t in ("a", "b", "c"))


# ------------------------------------------------------------------ watchlist
def test_watchlist_replace_is_last_write_wins_and_deduped(db, user):
    db.watchlist.replace(user.id, ["A", "B", "A"])
    assert [w.archetype_id for w in db.watchlist.list(user.id)] == ["A", "B"]

    db.watchlist.replace(user.id, ["C"])
    assert [w.archetype_id for w in db.watchlist.list(user.id)] == ["C"]


def test_subscribers_are_filtered_by_min_severity(db, user):
    db.watchlist.replace(user.id, ["FED"], min_severity="high")
    db.flush()
    assert db.watchlist.subscribers_for("FED", "high") == [user.id]
    assert db.watchlist.subscribers_for("FED", "watch") == []


# ------------------------------------------------------------------- holdings
def test_holdings_are_ciphertext_in_the_database(db, user):
    db.holdings.replace(user.id, {"TCS": 0.4, "INFY": 0.6})
    db.flush()

    raw = db.session.execute(text("SELECT symbol, weight FROM holdings")).fetchall()
    blob = b"".join(bytes(col) for row in raw for col in row)
    # The point of encrypting at rest is that a database dump reveals nothing.
    assert b"TCS" not in blob
    assert b"INFY" not in blob
    assert b"0.4" not in blob


def test_holdings_round_trip_through_encryption(db, user):
    db.holdings.replace(user.id, {"TCS": 0.4, "INFY": Decimal("0.6")})
    db.flush()
    got = {h.symbol: h.weight for h in db.holdings.list(user.id)}
    assert got == {"TCS": Decimal("0.4"), "INFY": Decimal("0.6")}


def test_every_holdings_read_writes_an_audit_row(db, user):
    db.holdings.replace(user.id, {"TCS": 1.0})
    db.flush()
    before = len(db.audit.recent(kind="holdings_access", limit=100))

    db.holdings.list(user.id)
    db.flush()
    after = db.audit.recent(kind="holdings_access", limit=100)
    assert len(after) == before + 1
    assert after[0].user_id == user.id


def test_holdings_fail_closed_without_a_key(db, user, monkeypatch):
    """A misconfigured deployment must refuse to store PII, not store it in the clear."""
    from impacto.config import reset_settings_cache

    monkeypatch.delenv("IMPACTO_HOLDINGS_ENCRYPTION_KEY", raising=False)
    reset_settings_cache()
    try:
        with pytest.raises(MissingEncryptionKey):
            db.holdings.replace(user.id, {"TCS": 1.0})
            db.flush()
    finally:
        reset_settings_cache()


# --------------------------------------------------------------------- push
def test_resubscribing_the_same_endpoint_repairs_rather_than_duplicates(db, user):
    db.push.subscribe(user.id, "https://push/1", "p1", "a1")
    db.push.record_failure("https://push/1")
    db.flush()

    db.push.subscribe(user.id, "https://push/1", "p2", "a2")
    db.flush()
    subs = db.push.list(user.id)
    assert len(subs) == 1
    assert subs[0].p256dh == "p2"
    assert subs[0].failed_count == 0


def test_subscription_is_pruned_after_three_gone_responses(db, user):
    db.push.subscribe(user.id, "https://push/2", "p", "a")
    db.flush()
    for _ in range(MAX_PUSH_FAILURES - 1):
        assert db.push.record_failure("https://push/2") is False
    assert db.push.record_failure("https://push/2") is True
    db.flush()
    assert db.push.list(user.id) == []


def test_a_successful_send_resets_the_failure_counter(db, user):
    db.push.subscribe(user.id, "https://push/3", "p", "a")
    db.push.record_failure("https://push/3")
    db.push.record_success("https://push/3")
    db.flush()
    assert db.push.list(user.id)[0].failed_count == 0


# ----------------------------------------------------------- analog summaries
def _summary(archetype="FED", target="NIFTY_IT", window="T+1..T+5", median=-180.0):
    return AnalogSummary(
        archetype_id=archetype,
        target=target,
        window=window,
        sample_size=12,
        mean_car_bps=-150.0,
        median_car_bps=median,
        stdev_bps=220.0,
        hit_rate=0.66,
        p5_bps=-500.0,
        p95_bps=120.0,
        t_stat=-2.1,
        p_value=0.043,
        analogs=[
            AnalogEvent(
                event_id="e1",
                event_date=date(2024, 1, 2),
                headline="h",
                similarity=0.9,
                car_bps=-100.0,
            )
        ],
    )


def test_analog_upsert_is_idempotent_on_its_primary_key(db):
    today = date.today()
    db.analogs.upsert(_summary(), as_of=today)
    db.analogs.upsert(_summary(median=-200.0), as_of=today)
    db.flush()
    assert db.analogs.count(as_of=today) == 1
    assert db.analogs.latest("FED", "NIFTY_IT", "T+1..T+5").median_car_bps == Decimal("-200.00")


def test_latest_picks_the_most_recent_as_of(db):
    db.analogs.upsert(_summary(median=-100.0), as_of=date.today() - timedelta(days=1))
    db.analogs.upsert(_summary(median=-300.0), as_of=date.today())
    db.flush()
    assert db.analogs.latest("FED", "NIFTY_IT", "T+1..T+5").median_car_bps == Decimal("-300.00")


def test_analog_detail_survives_the_json_round_trip(db):
    db.analogs.upsert(_summary(), as_of=date.today())
    db.flush()
    row = db.analogs.latest("FED", "NIFTY_IT", "T+1..T+5")
    assert row.analogs[0]["event_id"] == "e1"
    assert row.analogs[0]["car_bps"] == -100.0


def test_prune_drops_only_older_slices(db):
    today = date.today()
    db.analogs.upsert(_summary(), as_of=today - timedelta(days=10))
    db.analogs.upsert(_summary(), as_of=today)
    db.flush()
    assert db.analogs.prune_before(today) == 1
    db.flush()
    assert db.analogs.count() == 1


# ------------------------------------------------------------------- events
def _event(event_id="ev-1", day=None):
    return DetectedEvent(
        event_id=event_id,
        archetype_id="FED",
        event_date=day or date.today(),
        headline="Fed hikes",
        sources=["https://example/1"],
        matched_terms=["fed"],
        match_score=0.8,
    )


def test_event_upsert_is_idempotent_so_reruns_converge(db):
    db.events.upsert_many([_event(), _event()])
    db.events.upsert_many([_event()])
    db.flush()
    assert len(db.events.recent(date.today() - timedelta(days=1))) == 1


def test_existing_ids_identifies_what_is_already_known(db):
    db.events.upsert_many([_event("a"), _event("b")])
    db.flush()
    assert db.events.existing_ids(["a", "c"]) == {"a"}


def test_event_row_converts_back_to_the_domain_schema(db):
    db.events.upsert_many([_event()])
    db.flush()
    row = db.events.recent(date.today() - timedelta(days=1))[0]
    schema = db.events.to_schema(row)
    assert schema.event_id == "ev-1"
    assert schema.sources == ["https://example/1"]
    assert schema.match_score == pytest.approx(0.8)


def test_events_filter_by_archetype_and_range(db):
    db.events.upsert_many([_event("a", date(2026, 1, 1)), _event("b", date(2026, 6, 1))])
    db.flush()
    got = db.events.between(since=date(2026, 5, 1), archetype_id="FED")
    assert [r.event_id for r in got] == ["b"]


# ------------------------------------------------------------------- audit
def test_audit_rows_capture_the_compliance_evidence(db, user):
    row = db.audit.record(
        kind="explain",
        user_id=user.id,
        question="why did IT fall?",
        answer="Historically...",
        citations=[{"label": "Event: e1"}],
        compliance_flags=[],
        model="claude-opus-5",
        used_llm=True,
    )
    db.flush()
    stored = db.session.get(AuditLog, row.id)
    assert stored.used_llm is True
    assert stored.citations[0]["label"] == "Event: e1"
    assert stored.model == "claude-opus-5"


def test_audit_id_is_retrievable_for_the_rendered_beacon(db):
    row = db.audit.record(kind="explain", answer="a")
    db.flush()
    assert db.audit.get(row.id).id == row.id
    assert db.audit.get(uuid.uuid4()) is None

"""SQLAlchemy 2.0 typed models — the schema in §2.1 of the PWA build brief.

Three groups live here, with different lifetimes:
  * auth and personalisation  — owned by the user, deleted with them
  * precomputed analytics     — derived, rebuilt nightly, safe to drop and recompute
  * audit_log                 — SEBI evidence, retained five years, never rewritten
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .types import (
    EncryptedNumeric,
    EncryptedString,
    JsonB,
    TimestampTZ,
    UUIDType,
)


class Base(DeclarativeBase):
    pass


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


# ------------------------------------------------------------------------ auth
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=_uuid)
    # Stored lower-cased by the repository rather than using Postgres `citext`, so
    # the same uniqueness guarantee holds on SQLite and no extension is required.
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TimestampTZ, server_default=func.now())
    last_seen_at: Mapped[datetime | None] = mapped_column(TimestampTZ, nullable=True)
    locale: Mapped[str] = mapped_column(String(16), default="en-IN")
    tz: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")

    sessions: Mapped[list[AuthSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    watchlist: Mapped[list[WatchlistArchetype]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    holdings: Mapped[list[Holding]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    push_subscriptions: Mapped[list[PushSubscription]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class AuthSession(Base):
    """A refresh-token session. `sessions` in the brief; renamed in Python to avoid
    colliding with SQLAlchemy's own Session everywhere it is imported."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Only the hash is stored, so a database leak does not hand out live sessions.
    refresh_token_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(TimestampTZ, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Hashed, not stored raw: enough to spot session hijacking, not enough to track.
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TimestampTZ, server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(TimestampTZ, nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")

    __table_args__ = (Index("ix_sessions_user_expires", "user_id", "expires_at"),)


# -------------------------------------------------------------- personalisation
class WatchlistArchetype(Base):
    __tablename__ = "watchlist_archetypes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    archetype_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    min_severity: Mapped[str] = mapped_column(String(16), default="watch")
    created_at: Mapped[datetime] = mapped_column(TimestampTZ, server_default=func.now())

    user: Mapped[User] = relationship(back_populates="watchlist")


class Holding(Base):
    """Portfolio holdings. Encrypted at rest; see db/types.py.

    Reads are logged to audit_log by the repository, not here, so the obligation
    cannot be bypassed by constructing a query directly.
    """

    __tablename__ = "holdings"

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    weight: Mapped[Decimal] = mapped_column(EncryptedNumeric, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TimestampTZ, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TimestampTZ, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="holdings")


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    endpoint: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    p256dh: Mapped[str] = mapped_column(Text, nullable=False)
    auth: Mapped[str] = mapped_column(Text, nullable=False)
    ua: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TimestampTZ, server_default=func.now())
    # Pruned at 3 consecutive 410 Gone responses (§2.4).
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped[User] = relationship(back_populates="push_subscriptions")


# ------------------------------------------------------- precomputed analytics
class AnalogSummary(Base):
    """The hot read path.

    Computing these on request takes ~20 seconds for a full sweep, which is fine for
    a CLI and unacceptable for a phone. The nightly job fills this table so a request
    is a primary-key lookup.
    """

    __tablename__ = "analog_summaries"

    archetype_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target: Mapped[str] = mapped_column(String(64), primary_key=True)
    window: Mapped[str] = mapped_column(String(32), primary_key=True)
    as_of: Mapped[date] = mapped_column(Date, primary_key=True)

    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    mean_car_bps: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    median_car_bps: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    stdev_bps: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    hit_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    p5_bps: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    p95_bps: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    t_stat: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    p_value: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    analogs: Mapped[list] = mapped_column(JsonB, default=list)
    generated_at: Mapped[datetime] = mapped_column(TimestampTZ, server_default=func.now())

    __table_args__ = (
        Index("ix_analog_summaries_archetype_target", "archetype_id", "target"),
    )


class DetectedEventRow(Base):
    __tablename__ = "detected_events"

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    archetype_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[list] = mapped_column(JsonB, default=list)
    matched_terms: Mapped[list] = mapped_column(JsonB, default=list)
    match_score: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)
    surprise_magnitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TimestampTZ, server_default=func.now())

    __table_args__ = (Index("ix_detected_events_date_desc", event_date.desc()),)


class DailyDigest(Base):
    __tablename__ = "daily_digests"

    digest_date: Mapped[date] = mapped_column(Date, primary_key=True)
    payload: Mapped[dict] = mapped_column(JsonB, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(TimestampTZ, server_default=func.now())


class CalibrationRun(Base):
    """The honesty layer, versioned.

    Kept as history rather than overwritten so a rule that degrades over time is
    visible as a trend instead of a single snapshot.
    """

    __tablename__ = "calibration_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=_uuid)
    window: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    run_at: Mapped[datetime] = mapped_column(TimestampTZ, server_default=func.now())
    summary: Mapped[dict] = mapped_column(JsonB, nullable=False)
    rows: Mapped[list] = mapped_column(JsonB, nullable=False)


# ----------------------------------------------------------------------- audit
class AuditLog(Base):
    """Five-year record of every generated output and every holdings access.

    Append-only by convention — nothing in the repository layer updates or deletes a
    row. Retention is enforced by the operator (§2.1: five years plus one day).
    """

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    citations: Mapped[list] = mapped_column(JsonB, default=list)
    compliance_flags: Mapped[list] = mapped_column(JsonB, default=list)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    used_llm: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(TimestampTZ, server_default=func.now())

    __table_args__ = (Index("ix_audit_log_created_at", "created_at"),)


__all__ = [
    "Base",
    "User",
    "AuthSession",
    "WatchlistArchetype",
    "Holding",
    "PushSubscription",
    "AnalogSummary",
    "DetectedEventRow",
    "DailyDigest",
    "CalibrationRun",
    "AuditLog",
]

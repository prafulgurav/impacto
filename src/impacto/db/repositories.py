"""Repository layer.

Every database access in the application goes through one of these classes. Two
obligations are enforced here rather than left to callers:

  * holdings reads are written to `audit_log` (§2.6) — you cannot read a holding
    through this layer without producing an audit row;
  * emails are normalised to lower case, which is what makes the plain unique
    constraint behave like Postgres `citext` on both backends.
"""
from __future__ import annotations

import hashlib
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import Session

from ..models import AnalogSummary as AnalogSummarySchema
from ..models import DetectedEvent, Digest
from .models import (
    AnalogSummary,
    AuditLog,
    AuthSession,
    CalibrationRun,
    DailyDigest,
    DetectedEventRow,
    Holding,
    PushSubscription,
    User,
    WatchlistArchetype,
)
from .types import MissingEncryptionKey

MAX_PUSH_FAILURES = 3


def _now() -> datetime:
    return datetime.now(UTC)


def _upsert(session: Session, model, values: dict, keys: list[str]) -> None:
    """Insert-or-update on `keys`, using whichever dialect's ON CONFLICT applies.

    Postgres and SQLite both support ON CONFLICT DO UPDATE, so the jobs can be
    idempotent on either backend without a read-then-write race.
    """
    insert = pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
    stmt = insert(model).values(**values)
    updates = {k: stmt.excluded[k] for k in values if k not in keys}
    session.execute(stmt.on_conflict_do_update(index_elements=keys, set_=updates))


def hash_token(token: str) -> str:
    """Refresh tokens are stored hashed; a database leak must not yield live sessions."""
    return hashlib.sha256(token.encode()).hexdigest()


def hash_ip(ip: str | None) -> str | None:
    """Enough to spot a session moving between networks, not enough to track a user."""
    return hashlib.sha256(ip.encode()).hexdigest()[:32] if ip else None


# --------------------------------------------------------------------- users
class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def normalise(email: str) -> str:
        return email.strip().lower()

    def get(self, user_id: uuid.UUID) -> User | None:
        return self.session.get(User, user_id)

    def by_email(self, email: str) -> User | None:
        return self.session.scalar(
            select(User).where(User.email == self.normalise(email))
        )

    def upsert_by_email(self, email: str, **fields: Any) -> User:
        """Get-or-create. Used by both auth paths, which are inherently idempotent."""
        user = self.by_email(email)
        if user is None:
            user = User(email=self.normalise(email), **fields)
            self.session.add(user)
            self.session.flush()
        else:
            for key, value in fields.items():
                setattr(user, key, value)
        user.last_seen_at = _now()
        return user

    def delete(self, user_id: uuid.UUID) -> bool:
        user = self.get(user_id)
        if user is None:
            return False
        self.session.delete(user)
        return True


class AuthSessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        user_id: uuid.UUID,
        refresh_token: str,
        ttl_days: int,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> AuthSession:
        row = AuthSession(
            user_id=user_id,
            refresh_token_hash=hash_token(refresh_token),
            expires_at=_now() + timedelta(days=ttl_days),
            user_agent=user_agent,
            ip_hash=hash_ip(ip),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def by_token(self, refresh_token: str) -> AuthSession | None:
        """Return the session only if it is live — expired and revoked both miss."""
        row = self.session.scalar(
            select(AuthSession).where(
                AuthSession.refresh_token_hash == hash_token(refresh_token)
            )
        )
        if row is None or row.revoked_at is not None:
            return None
        expires = row.expires_at
        if expires.tzinfo is None:  # SQLite returns naive datetimes
            expires = expires.replace(tzinfo=UTC)
        return None if expires <= _now() else row

    def revoke(self, refresh_token: str) -> bool:
        row = self.session.scalar(
            select(AuthSession).where(
                AuthSession.refresh_token_hash == hash_token(refresh_token)
            )
        )
        if row is None:
            return False
        row.revoked_at = _now()
        return True

    def revoke_all(self, user_id: uuid.UUID) -> int:
        rows = self.session.scalars(
            select(AuthSession).where(
                AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None)
            )
        ).all()
        for row in rows:
            row.revoked_at = _now()
        return len(rows)

    def purge_expired(self) -> int:
        result = self.session.execute(
            delete(AuthSession).where(AuthSession.expires_at <= _now())
        )
        return result.rowcount or 0


# ------------------------------------------------------------- personalisation
class WatchlistRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self, user_id: uuid.UUID) -> list[WatchlistArchetype]:
        return list(
            self.session.scalars(
                select(WatchlistArchetype)
                .where(WatchlistArchetype.user_id == user_id)
                .order_by(WatchlistArchetype.archetype_id)
            )
        )

    def replace(
        self, user_id: uuid.UUID, archetype_ids: list[str], min_severity: str = "watch"
    ) -> list[WatchlistArchetype]:
        """Last-write-wins, matching the offline outbox's conflict rule (§5.2)."""
        self.session.execute(
            delete(WatchlistArchetype).where(WatchlistArchetype.user_id == user_id)
        )
        for archetype_id in dict.fromkeys(archetype_ids):  # de-dupe, keep order
            self.session.add(
                WatchlistArchetype(
                    user_id=user_id, archetype_id=archetype_id, min_severity=min_severity
                )
            )
        self.session.flush()
        return self.list(user_id)

    def subscribers_for(self, archetype_id: str, severity: str) -> list[uuid.UUID]:
        """Users whose watchlist covers this archetype at or below `severity`."""
        order = {"info": 0, "watch": 1, "high": 2}
        level = order.get(severity, 0)
        rows = self.session.scalars(
            select(WatchlistArchetype).where(
                WatchlistArchetype.archetype_id == archetype_id
            )
        ).all()
        return [r.user_id for r in rows if order.get(r.min_severity, 1) <= level]


@dataclass(frozen=True)
class HoldingRecord:
    """A decrypted holding. Deliberately a plain value object so nothing downstream
    holds a live ORM row wired to encrypted columns."""

    id: uuid.UUID
    symbol: str
    weight: Decimal
    updated_at: datetime | None = None


@contextmanager
def _unwrap_crypto_errors():
    """Surface a key problem as MissingEncryptionKey, not a SQLAlchemy error.

    The encryption failure happens inside a bind/result processor, so SQLAlchemy
    wraps it in StatementError. Callers outside `impacto.db` should never have to
    know that — the API turns MissingEncryptionKey into a 503.
    """
    try:
        yield
    except StatementError as exc:
        if isinstance(exc.orig, MissingEncryptionKey):
            raise exc.orig from exc
        raise


class HoldingsRepository:
    """Holdings are financial PII. Every read here writes an audit row (§2.6)."""

    def __init__(self, session: Session, audit: AuditRepository) -> None:
        self.session = session
        self._audit = audit

    def list(self, user_id: uuid.UUID, reason: str = "read") -> list[HoldingRecord]:
        with _unwrap_crypto_errors():
            rows = self.session.scalars(
                select(Holding).where(Holding.user_id == user_id).order_by(Holding.created_at)
            ).all()
        self._audit.record(
            kind="holdings_access",
            user_id=user_id,
            question=reason,
            answer=f"{len(rows)} holdings read",
        )
        return [
            HoldingRecord(id=r.id, symbol=r.symbol, weight=r.weight, updated_at=r.updated_at)
            for r in rows
        ]

    def replace(
        self, user_id: uuid.UUID, holdings: dict[str, float | Decimal]
    ) -> list[HoldingRecord]:
        self.session.execute(delete(Holding).where(Holding.user_id == user_id))
        for symbol, weight in holdings.items():
            self.session.add(
                Holding(user_id=user_id, symbol=symbol, weight=Decimal(str(weight)))
            )
        with _unwrap_crypto_errors():
            self.session.flush()
        self._audit.record(
            kind="holdings_write",
            user_id=user_id,
            answer=f"{len(holdings)} holdings written",
        )
        return self.list(user_id, reason="post-write read-back")

    def clear(self, user_id: uuid.UUID) -> int:
        result = self.session.execute(delete(Holding).where(Holding.user_id == user_id))
        self._audit.record(kind="holdings_delete", user_id=user_id)
        return result.rowcount or 0


class PushSubscriptionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def subscribe(
        self, user_id: uuid.UUID, endpoint: str, p256dh: str, auth: str, ua: str | None = None
    ) -> PushSubscription:
        existing = self.session.scalar(
            select(PushSubscription).where(PushSubscription.endpoint == endpoint)
        )
        if existing is not None:
            # Browsers re-issue the same endpoint after a permission re-grant; treat
            # that as a repair, not a duplicate, and reset the failure counter.
            existing.user_id = user_id
            existing.p256dh, existing.auth, existing.ua = p256dh, auth, ua
            existing.failed_count = 0
            return existing
        row = PushSubscription(
            user_id=user_id, endpoint=endpoint, p256dh=p256dh, auth=auth, ua=ua
        )
        self.session.add(row)
        self.session.flush()
        return row

    def list(self, user_id: uuid.UUID) -> list[PushSubscription]:
        return list(
            self.session.scalars(
                select(PushSubscription).where(PushSubscription.user_id == user_id)
            )
        )

    def unsubscribe(self, endpoint: str) -> bool:
        result = self.session.execute(
            delete(PushSubscription).where(PushSubscription.endpoint == endpoint)
        )
        return bool(result.rowcount)

    def record_failure(self, endpoint: str) -> bool:
        """Count a 410 Gone. Returns True when the subscription was pruned (§2.4)."""
        row = self.session.scalar(
            select(PushSubscription).where(PushSubscription.endpoint == endpoint)
        )
        if row is None:
            return False
        row.failed_count += 1
        if row.failed_count >= MAX_PUSH_FAILURES:
            self.session.delete(row)
            return True
        return False

    def record_success(self, endpoint: str) -> None:
        row = self.session.scalar(
            select(PushSubscription).where(PushSubscription.endpoint == endpoint)
        )
        if row is not None:
            row.failed_count = 0


# ------------------------------------------------------- precomputed analytics
class AnalogSummaryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, summary: AnalogSummarySchema, as_of: date) -> None:
        _upsert(
            self.session,
            AnalogSummary,
            {
                "archetype_id": summary.archetype_id,
                "target": summary.target,
                "window": summary.window,
                "as_of": as_of,
                "sample_size": summary.sample_size,
                "mean_car_bps": Decimal(str(summary.mean_car_bps)),
                "median_car_bps": Decimal(str(summary.median_car_bps)),
                "stdev_bps": Decimal(str(summary.stdev_bps)),
                "hit_rate": Decimal(str(summary.hit_rate)),
                "p5_bps": Decimal(str(summary.p5_bps)),
                "p95_bps": Decimal(str(summary.p95_bps)),
                "t_stat": Decimal(str(summary.t_stat)),
                "p_value": Decimal(str(summary.p_value)),
                "analogs": [a.model_dump(mode="json") for a in summary.analogs],
                "generated_at": _now(),
            },
            keys=["archetype_id", "target", "window", "as_of"],
        )

    def latest(
        self, archetype_id: str, target: str, window: str
    ) -> AnalogSummary | None:
        """Most recent precompute for this triple. The read path never recomputes."""
        return self.session.scalar(
            select(AnalogSummary)
            .where(
                AnalogSummary.archetype_id == archetype_id,
                AnalogSummary.target == target,
                AnalogSummary.window == window,
            )
            .order_by(AnalogSummary.as_of.desc())
            .limit(1)
        )

    def for_window(self, window: str, as_of: date | None = None) -> list[AnalogSummary]:
        stmt = select(AnalogSummary).where(AnalogSummary.window == window)
        if as_of is not None:
            stmt = stmt.where(AnalogSummary.as_of == as_of)
        return list(
            self.session.scalars(
                stmt.order_by(AnalogSummary.archetype_id, AnalogSummary.target)
            )
        )

    def count(self, as_of: date | None = None) -> int:
        from sqlalchemy import func as sa_func

        stmt = select(sa_func.count()).select_from(AnalogSummary)
        if as_of is not None:
            stmt = stmt.where(AnalogSummary.as_of == as_of)
        return int(self.session.scalar(stmt) or 0)

    def latest_as_of(self) -> date | None:
        from sqlalchemy import func as sa_func

        return self.session.scalar(select(sa_func.max(AnalogSummary.as_of)))

    def prune_before(self, cutoff: date) -> int:
        """Yesterday's precompute is dead weight once today's has landed."""
        result = self.session.execute(
            delete(AnalogSummary).where(AnalogSummary.as_of < cutoff)
        )
        return result.rowcount or 0


class DetectedEventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_many(self, events: list[DetectedEvent]) -> int:
        """Idempotent by `event_id`, so re-running ingest never duplicates."""
        for ev in events:
            _upsert(
                self.session,
                DetectedEventRow,
                {
                    "event_id": ev.event_id,
                    "archetype_id": ev.archetype_id,
                    "event_date": ev.event_date,
                    "headline": ev.headline,
                    "sources": list(ev.sources),
                    "matched_terms": list(ev.matched_terms),
                    "match_score": Decimal(str(ev.match_score)),
                    "surprise_magnitude": (
                        Decimal(str(ev.surprise_magnitude))
                        if ev.surprise_magnitude is not None
                        else None
                    ),
                },
                keys=["event_id"],
            )
        return len(events)

    def existing_ids(self, event_ids: list[str]) -> set[str]:
        if not event_ids:
            return set()
        rows = self.session.scalars(
            select(DetectedEventRow.event_id).where(
                DetectedEventRow.event_id.in_(event_ids)
            )
        ).all()
        return set(rows)

    def recent(self, since: date, limit: int = 500) -> list[DetectedEventRow]:
        return list(
            self.session.scalars(
                select(DetectedEventRow)
                .where(DetectedEventRow.event_date >= since)
                .order_by(DetectedEventRow.event_date.desc())
                .limit(limit)
            )
        )

    def between(
        self,
        since: date | None = None,
        until: date | None = None,
        archetype_id: str | None = None,
        limit: int = 50,
    ) -> list[DetectedEventRow]:
        stmt = select(DetectedEventRow)
        if since is not None:
            stmt = stmt.where(DetectedEventRow.event_date >= since)
        if until is not None:
            stmt = stmt.where(DetectedEventRow.event_date <= until)
        if archetype_id is not None:
            stmt = stmt.where(DetectedEventRow.archetype_id == archetype_id)
        return list(
            self.session.scalars(
                stmt.order_by(DetectedEventRow.event_date.desc()).limit(limit)
            )
        )

    @staticmethod
    def to_schema(row: DetectedEventRow) -> DetectedEvent:
        return DetectedEvent(
            event_id=row.event_id,
            archetype_id=row.archetype_id,
            event_date=row.event_date,
            headline=row.headline,
            sources=list(row.sources or []),
            matched_terms=list(row.matched_terms or []),
            match_score=float(row.match_score or 0),
            surprise_magnitude=(
                float(row.surprise_magnitude)
                if row.surprise_magnitude is not None
                else None
            ),
        )


class DigestRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, digest: Digest) -> None:
        _upsert(
            self.session,
            DailyDigest,
            {
                "digest_date": digest.digest_date,
                "payload": digest.model_dump(mode="json"),
                "generated_at": _now(),
            },
            keys=["digest_date"],
        )

    def get(self, digest_date: date) -> DailyDigest | None:
        return self.session.get(DailyDigest, digest_date)

    def latest(self) -> DailyDigest | None:
        return self.session.scalar(
            select(DailyDigest).order_by(DailyDigest.digest_date.desc()).limit(1)
        )


class CalibrationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record(self, window: str, summary: dict, rows: list[dict]) -> CalibrationRun:
        run = CalibrationRun(window=window, summary=summary, rows=rows)
        self.session.add(run)
        self.session.flush()
        return run

    def latest(self, window: str) -> CalibrationRun | None:
        return self.session.scalar(
            select(CalibrationRun)
            .where(CalibrationRun.window == window)
            .order_by(CalibrationRun.run_at.desc())
            .limit(1)
        )


class AuditRepository:
    """Append-only. Nothing here updates or deletes; retention is the operator's job."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def record(
        self,
        kind: str,
        user_id: uuid.UUID | None = None,
        question: str | None = None,
        answer: str | None = None,
        citations: list | None = None,
        compliance_flags: list | None = None,
        model: str | None = None,
        used_llm: bool = False,
    ) -> AuditLog:
        row = AuditLog(
            kind=kind,
            user_id=user_id,
            question=question,
            answer=answer,
            citations=citations or [],
            compliance_flags=compliance_flags or [],
            model=model,
            used_llm=used_llm,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def get(self, audit_id: uuid.UUID) -> AuditLog | None:
        return self.session.get(AuditLog, audit_id)

    def recent(self, kind: str | None = None, limit: int = 50) -> list[AuditLog]:
        stmt = select(AuditLog)
        if kind is not None:
            stmt = stmt.where(AuditLog.kind == kind)
        return list(
            self.session.scalars(stmt.order_by(AuditLog.created_at.desc()).limit(limit))
        )


# ------------------------------------------------------------------- facade
class Repositories:
    """One handle over a single transaction. This is what callers receive."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.audit = AuditRepository(session)
        self.users = UserRepository(session)
        self.auth_sessions = AuthSessionRepository(session)
        self.watchlist = WatchlistRepository(session)
        self.holdings = HoldingsRepository(session, self.audit)
        self.push = PushSubscriptionRepository(session)
        self.analogs = AnalogSummaryRepository(session)
        self.events = DetectedEventRepository(session)
        self.digests = DigestRepository(session)
        self.calibration = CalibrationRepository(session)

    def flush(self) -> None:
        self.session.flush()


__all__ = [
    "Repositories",
    "HoldingRecord",
    "MAX_PUSH_FAILURES",
    "hash_token",
    "hash_ip",
]

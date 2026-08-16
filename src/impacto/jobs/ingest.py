"""Event ingestion — every 30 minutes during 06:00–23:00 IST.

GDELT and RSS in, classified `detected_events` out. The job is idempotent: events
are upserted by `event_id`, so a re-run after a partial failure converges rather
than duplicating. New events above the severity threshold are returned for push
fan-out; the job itself does not send, so a notification bug cannot corrupt data.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date, timedelta

from ..db import Repositories
from ..models import DetectedEvent
from ..service import Impacto

log = logging.getLogger(__name__)

_SEVERITY_ORDER = {"info": 0, "watch": 1, "high": 2}


@dataclass
class IngestResult:
    detected: int = 0
    new: int = 0
    updated: int = 0
    alerts: list = field(default_factory=list)
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def run_ingest(
    service: Impacto,
    repos: Repositories,
    since: date | None = None,
    until: date | None = None,
    lookback_days: int = 2,
    min_severity: str = "high",
) -> IngestResult:
    """Fetch, classify and persist. Returns the alerts worth notifying about.

    The lookback overlaps deliberately: a source that publishes late would otherwise
    fall through the gap between two 30-minute runs.
    """
    started = time.perf_counter()
    result = IngestResult()
    until = until or date.today()
    since = since or until - timedelta(days=lookback_days)

    try:
        events: list[DetectedEvent] = service.detect(since, until)
    except Exception as exc:
        # A news source being down is routine and must not take the scheduler with it.
        result.errors.append(f"detect failed: {exc}")
        result.duration_seconds = time.perf_counter() - started
        log.warning("ingest detect failed: %s", exc)
        return result

    result.detected = len(events)
    if not events:
        result.duration_seconds = time.perf_counter() - started
        return result

    known = repos.events.existing_ids([e.event_id for e in events])
    fresh = [e for e in events if e.event_id not in known]
    result.new = len(fresh)
    result.updated = len(events) - len(fresh)
    repos.events.upsert_many(events)

    # Only genuinely new events can raise an alert. Re-classifying an event we
    # already told the user about would notify them twice for one occurrence.
    if fresh:
        threshold = _SEVERITY_ORDER.get(min_severity, 2)
        for alert in service.alerts.build_many(fresh, min_severity="info"):
            if _SEVERITY_ORDER.get(alert.severity, 0) >= threshold:
                result.alerts.append(alert)

    result.duration_seconds = time.perf_counter() - started
    log.info(
        "ingest detected=%d new=%d alerts=%d in %.1fs",
        result.detected,
        result.new,
        len(result.alerts),
        result.duration_seconds,
    )
    return result


def push_targets(repos: Repositories, alerts: list) -> dict[str, list]:
    """Map each alert to the users watching its archetype at that severity.

    Returns alert_id -> user ids. The payload itself is built by the push layer and
    deliberately carries no numbers (§2.4): a stale figure on a lock screen is
    exactly the misleading output the compliance architecture exists to prevent.
    """
    out: dict[str, list] = {}
    for alert in alerts:
        out[alert.alert_id] = repos.watchlist.subscribers_for(
            alert.archetype_id, alert.severity
        )
    return out


__all__ = ["run_ingest", "push_targets", "IngestResult"]

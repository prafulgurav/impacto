"""Daily digest — 07:30 IST on weekdays, ahead of the 09:15 open.

Builds the digest for the trailing session and stores it, so the first request of
the morning — and every offline launch — is served from a row rather than a
computation.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date

from ..config import get_settings
from ..db import Repositories
from ..service import Impacto

log = logging.getLogger(__name__)


@dataclass
class DigestResult:
    digest_date: date
    events: int = 0
    sections: int = 0
    subscribers: int = 0
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def run_digest(
    service: Impacto,
    repos: Repositories,
    day: date | None = None,
    lookback_days: int | None = None,
) -> DigestResult:
    """Build and store the digest for `day`, defaulting to the latest event date."""
    started = time.perf_counter()
    lookback_days = lookback_days or get_settings().digest_lookback_days
    day = day or service.latest_event_date()
    result = DigestResult(digest_date=day)

    try:
        events = service.events_on(day, lookback_days)
        digest = service.digests.build(events, digest_date=day)
    except Exception as exc:
        result.errors.append(f"digest build failed: {exc}")
        result.duration_seconds = time.perf_counter() - started
        log.warning("digest build failed for %s: %s", day, exc)
        return result

    repos.digests.upsert(digest)
    result.events = len(digest.events)
    result.sections = len(digest.sections)
    result.subscribers = len(digest_subscribers(repos, digest))
    result.duration_seconds = time.perf_counter() - started
    log.info(
        "digest %s events=%d sections=%d in %.1fs",
        day,
        result.events,
        result.sections,
        result.duration_seconds,
    )
    return result


def digest_subscribers(repos: Repositories, digest) -> list:
    """Users whose watchlist matches at least one archetype in today's digest.

    De-duplicated, because a digest covering three archetypes a user watches is
    still one notification.
    """
    seen: dict = {}
    for event in digest.events:
        for user_id in repos.watchlist.subscribers_for(event.archetype_id, "info"):
            seen[user_id] = True
    return list(seen)


__all__ = ["run_digest", "digest_subscribers", "DigestResult"]

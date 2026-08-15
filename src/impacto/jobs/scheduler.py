"""APScheduler wiring.

In-process and single-instance by design (§2.2). Celery or Arq only become the right
answer with more than one API replica, and reaching for them now would buy a broker,
a worker fleet and a deployment story for three cron jobs.

Every job opens its own transaction and swallows its own exceptions, so a failed run
is logged and the schedule survives it.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from ..config import get_settings
from ..db import repositories
from ..service import Impacto, get_service
from .digest import run_digest
from .ingest import push_targets, run_ingest
from .precompute import run_calibration, run_precompute

log = logging.getLogger(__name__)


def _guard(name: str, fn: Callable[[Impacto, Any], Any]) -> Callable[[], Any]:
    """Wrap a job so a failure is logged rather than killing the scheduler thread."""

    def runner() -> Any:
        try:
            with repositories() as repos:
                return fn(get_service(), repos)
        except Exception:
            log.exception("scheduled job %s failed", name)
            return None

    runner.__name__ = f"job_{name}"
    return runner


def _precompute_job(service: Impacto, repos) -> Any:
    result = run_precompute(service, repos)
    # Calibration reads the same event studies the sweep just warmed, so it is far
    # cheaper here than as a job of its own.
    run_calibration(service, repos)
    return result


def _ingest_job(service: Impacto, repos) -> Any:
    result = run_ingest(service, repos)
    if result.alerts:
        # Fan-out targets are computed here; the push send itself lives in the API
        # layer so a notification failure cannot roll back ingested events.
        result.push_targets = push_targets(repos, result.alerts)
    return result


def build_scheduler(scheduler: BackgroundScheduler | None = None) -> BackgroundScheduler:
    """Register the three jobs from §2.2 on an IST-pinned scheduler."""
    s = get_settings()
    sched = scheduler or BackgroundScheduler(timezone=s.scheduler_timezone)

    sched.add_job(
        _guard("precompute", _precompute_job),
        CronTrigger(
            hour=s.precompute_hour,
            minute=s.precompute_minute,
            timezone=s.scheduler_timezone,
        ),
        id="precompute",
        replace_existing=True,
        max_instances=1,
        coalesce=True,  # a missed 02:00 run fires once, not once per missed slot
    )

    sched.add_job(
        _guard("ingest", _ingest_job),
        CronTrigger(
            hour=f"{s.ingest_start_hour}-{s.ingest_end_hour}",
            minute=f"*/{s.ingest_interval_minutes}",
            timezone=s.scheduler_timezone,
        ),
        id="ingest",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    sched.add_job(
        _guard("digest", lambda service, repos: run_digest(service, repos)),
        CronTrigger(
            day_of_week="mon-fri",
            hour=s.digest_hour,
            minute=s.digest_minute,
            timezone=s.scheduler_timezone,
        ),
        id="digest",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    return sched


def start_scheduler() -> BackgroundScheduler | None:
    """Start the scheduler if enabled. Returns None when it is switched off.

    Off by default so tests, CLI use and a second API replica do not each run the
    jobs independently.
    """
    if not get_settings().scheduler_enabled:
        log.info("scheduler disabled (IMPACTO_SCHEDULER_ENABLED=false)")
        return None
    sched = build_scheduler()
    sched.start()
    log.info("scheduler started: %s", [j.id for j in sched.get_jobs()])
    return sched


__all__ = ["build_scheduler", "start_scheduler"]

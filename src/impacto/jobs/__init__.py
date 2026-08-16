"""Scheduled work.

Three jobs, per §2.2 of the PWA build brief:

  precompute  02:00 IST daily        analog_summaries for every archetype/target/window
  ingest      every 30 min, 06-23    GDELT + RSS -> classify -> detected_events
  digest      07:30 IST weekdays     build and store the daily digest

Each is a plain function taking (service, repositories), so it can be called from a
test, the CLI, or the scheduler with identical behaviour.
"""
from __future__ import annotations

from .digest import DigestResult, digest_subscribers, run_digest
from .ingest import IngestResult, push_targets, run_ingest
from .precompute import PrecomputeResult, run_calibration, run_precompute
from .scheduler import build_scheduler, start_scheduler

__all__ = [
    "run_precompute",
    "run_calibration",
    "PrecomputeResult",
    "run_ingest",
    "push_targets",
    "IngestResult",
    "run_digest",
    "digest_subscribers",
    "DigestResult",
    "build_scheduler",
    "start_scheduler",
]

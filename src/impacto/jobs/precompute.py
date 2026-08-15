"""Nightly precompute — 02:00 IST.

The API used to compute analog summaries on request: roughly 20 seconds for a full
sweep. That is fine for a CLI and unusable on a phone over 4G. This job fills
`analog_summaries` for every (archetype, target, window) triple so the read path is
a primary-key lookup, and the mobile client can serve it from cache besides.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date, timedelta

from ..config import get_settings
from ..db import Repositories
from ..service import Impacto

log = logging.getLogger(__name__)


@dataclass
class PrecomputeResult:
    as_of: date
    rows_written: int = 0
    combinations: int = 0
    skipped_no_data: int = 0
    pruned: int = 0
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def run_precompute(
    service: Impacto,
    repos: Repositories,
    as_of: date | None = None,
    windows: list[str] | None = None,
    keep_days: int | None = None,
    archetype_ids: list[str] | None = None,
) -> PrecomputeResult:
    """Fill `analog_summaries` for every archetype/target/window combination.

    A single failing combination is recorded and skipped rather than aborting the
    sweep — one bad pair must not cost the whole night's precompute.

    `archetype_ids` narrows the sweep, which is what you want after editing one
    transmission rule: recomputing 15 archetypes to check a change to one is a
    waste of two minutes.
    """
    settings = get_settings()
    as_of = as_of or date.today()
    windows = windows or settings.analog_window_list
    started = time.perf_counter()
    result = PrecomputeResult(as_of=as_of)

    selected = (
        [service.kb.archetypes[a] for a in archetype_ids if a in service.kb.archetypes]
        if archetype_ids is not None
        else list(service.kb.archetypes.values())
    )

    for archetype in selected:
        for impact in archetype.impacts:
            for window in windows:
                result.combinations += 1
                try:
                    summary = service.analogs.summarise(
                        archetype.id,
                        impact.target,
                        window,
                        expected_direction=impact.direction,
                    )
                except (KeyError, ValueError) as exc:
                    result.errors.append(f"{archetype.id}/{impact.target}/{window}: {exc}")
                    continue
                if summary is None or summary.sample_size == 0:
                    # No usable history for this pair yet. The UI renders the
                    # mechanism-only state, so an absent row is a valid outcome.
                    result.skipped_no_data += 1
                    continue
                repos.analogs.upsert(summary, as_of=as_of)
                result.rows_written += 1

    keep_days = settings.precompute_keep_days if keep_days is None else keep_days
    if keep_days > 0:
        result.pruned = repos.analogs.prune_before(as_of - timedelta(days=keep_days))

    result.duration_seconds = time.perf_counter() - started
    log.info(
        "precompute as_of=%s rows=%d/%d skipped=%d pruned=%d in %.1fs",
        as_of,
        result.rows_written,
        result.combinations,
        result.skipped_no_data,
        result.pruned,
        result.duration_seconds,
    )
    return result


def run_calibration(
    service: Impacto, repos: Repositories, windows: list[str] | None = None
) -> int:
    """Score every encoded prior against realised history and store the run.

    Kept as history rather than a single current snapshot, so a rule that decays
    over time shows up as a trend on /calibration instead of a surprise.
    """
    windows = windows or [get_settings().default_window]
    for window in windows:
        rows = service.analogs.calibration_report(window)
        counts: dict[str, int] = {}
        for row in rows:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        repos.calibration.record(window=window, summary=counts, rows=rows)
    return len(windows)


__all__ = ["run_precompute", "run_calibration", "PrecomputeResult"]

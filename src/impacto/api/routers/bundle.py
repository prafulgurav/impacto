"""GET /bundle/offline — everything the PWA needs, in one round trip (§3).

This is the offline-first workhorse. On app open and on the `online` event the
client sends `If-None-Match`; a 304 costs one small round trip and the app paints
from IndexedDB. On 200 the client writes the whole payload in a single Dexie
transaction.

Target is under 300 KB gzipped. When the full payload exceeds that, the per-analog
detail arrays are dropped and fetched per view instead — the summary statistics
every screen needs are kept, and `analogDetailOmitted` tells the client to fetch
detail on demand rather than silently rendering an empty distribution.
"""
from __future__ import annotations

import gzip
import json
import logging
from datetime import date, timedelta

from fastapi import APIRouter, Header, Request, Response

from ...explain.guardrails import DISCLAIMER
from ..cache import cache_control, compute_etag, etag_matches, get_cache
from ..deps import ReposDep, ServiceDep, SettingsDep

log = logging.getLogger(__name__)
router = APIRouter(tags=["bundle"])

CACHE_KEY = "bundle:offline:v1"


def _archetypes(service) -> list[dict]:
    return [
        {
            "id": a.id,
            "label": a.label,
            "family": a.family,
            "description": " ".join(a.description.split()),
            "detection": a.detection.model_dump(),
            "impacts": [
                {**i.model_dump(), "rationale": " ".join(i.rationale.split())}
                for i in a.impacts
            ],
        }
        for a in service.kb.archetypes.values()
    ]


def _channels(service) -> list[dict]:
    return [
        {**c.model_dump(), "description": " ".join(c.description.split())}
        for c in service.kb.channels.values()
    ]


def _analog_rows(repos, window: str) -> list[dict]:
    return [
        {
            "archetypeId": r.archetype_id,
            "target": r.target,
            "window": r.window,
            "asOf": r.as_of.isoformat(),
            "sampleSize": r.sample_size,
            "meanCarBps": float(r.mean_car_bps),
            "medianCarBps": float(r.median_car_bps),
            "stdevBps": float(r.stdev_bps),
            "hitRate": float(r.hit_rate),
            "p5Bps": float(r.p5_bps),
            "p95Bps": float(r.p95_bps),
            "tStat": float(r.t_stat),
            "pValue": float(r.p_value),
            "analogs": r.analogs or [],
        }
        for r in repos.analogs.for_window(window)
    ]


def _events(repos, days: int) -> list[dict]:
    since = date.today() - timedelta(days=days)
    return [
        {
            "eventId": r.event_id,
            "archetypeId": r.archetype_id,
            "eventDate": r.event_date.isoformat(),
            "headline": r.headline,
            "sources": r.sources or [],
            "matchScore": float(r.match_score or 0),
        }
        for r in repos.events.recent(since, limit=500)
    ]


def _gzipped_size(payload: dict) -> int:
    raw = json.dumps(payload, separators=(",", ":"), default=str).encode()
    return len(gzip.compress(raw, compresslevel=6))


def build_bundle(service, repos, settings) -> dict:
    """Assemble the payload, shedding analog detail if it blows the size budget."""
    window = settings.default_window
    latest_digest = repos.digests.latest()

    bundle = {
        "generatedAt": (
            repos.analogs.latest_as_of().isoformat()
            if repos.analogs.latest_as_of()
            else date.today().isoformat()
        ),
        "defaultWindow": window,
        "archetypes": _archetypes(service),
        "channels": _channels(service),
        "analogSummaries": _analog_rows(repos, window),
        "digest": latest_digest.payload if latest_digest else None,
        "recentEvents": _events(repos, settings.bundle_event_days),
        "disclaimer": DISCLAIMER,
        "analogDetailOmitted": False,
    }

    size = _gzipped_size(bundle)
    if size > settings.bundle_max_bytes:
        for row in bundle["analogSummaries"]:
            row["analogs"] = []
        bundle["analogDetailOmitted"] = True
        shed = _gzipped_size(bundle)
        log.warning(
            "offline bundle was %d bytes gzipped (budget %d); dropped per-analog "
            "detail arrays, now %d bytes",
            size,
            settings.bundle_max_bytes,
            shed,
        )
        size = shed

    bundle["gzippedBytes"] = size
    return bundle


@router.get("/bundle/offline")
def offline_bundle(
    request: Request,
    service: ServiceDep,
    repos: ReposDep,
    settings: SettingsDep,
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
) -> Response:
    cache = get_cache()
    payload = cache.get_json(CACHE_KEY)
    if payload is None:
        payload = build_bundle(service, repos, settings)
        cache.set_json(CACHE_KEY, payload, settings.cache_ttl_bundle)

    etag = compute_etag(payload)
    headers = {
        "ETag": etag,
        "Cache-Control": cache_control(settings.cache_ttl_bundle),
        "X-Bundle-Gzipped-Bytes": str(payload.get("gzippedBytes", 0)),
    }
    if etag_matches(if_none_match, etag):
        # Nothing changed since the client's last sync. This is the common case on
        # every app open, so it must stay cheap.
        return Response(status_code=304, headers=headers)

    return Response(
        content=json.dumps(payload, separators=(",", ":"), default=str),
        media_type="application/json",
        headers=headers,
    )


__all__ = ["router", "build_bundle", "CACHE_KEY"]

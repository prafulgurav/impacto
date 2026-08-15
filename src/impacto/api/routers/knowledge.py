"""Public read endpoints — knowledge, events, impact, event study, alerts, digest.

All anonymous, all cacheable, all carrying an ETag so the service worker can
revalidate for the price of a 304. These pages are the SEO and LLM-citation
surface, so gating them behind a login would close the acquisition channel (§2.3).
"""
from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Header, HTTPException, Query, Response

from ...eventstudy.car import InsufficientData, parse_window
from ...explain.guardrails import DISCLAIMER
from ...models import Alert, Digest, ImpactScore
from ..cache import cache_control, compute_etag, etag_matches
from ..deps import ReposDep, ServiceDep, SettingsDep

router = APIRouter(tags=["public"])


def conditional(payload, ttl: int, if_none_match: str | None) -> Response:
    """Serialise with an ETag, answering 304 when the client is already current."""
    etag = compute_etag(payload)
    headers = {"ETag": etag, "Cache-Control": cache_control(ttl)}
    if etag_matches(if_none_match, etag):
        return Response(status_code=304, headers=headers)
    return Response(
        content=json.dumps(payload, separators=(",", ":"), default=str),
        media_type="application/json",
        headers=headers,
    )


# ------------------------------------------------------------------ knowledge
@router.get("/knowledge/archetypes")
def archetypes(
    service: ServiceDep,
    settings: SettingsDep,
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
) -> Response:
    payload = [
        {
            "id": a.id,
            "label": a.label,
            "family": a.family,
            "description": " ".join(a.description.split()),
            "n_impacts": len(a.impacts),
            "targets": [i.target for i in a.impacts],
        }
        for a in service.kb.archetypes.values()
    ]
    return conditional(payload, settings.cache_ttl_knowledge, if_none_match)


@router.get("/knowledge/archetypes/{archetype_id}")
def archetype(
    archetype_id: str,
    service: ServiceDep,
    settings: SettingsDep,
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
) -> Response:
    try:
        a = service.kb.archetype(archetype_id)
    except KeyError as exc:
        raise HTTPException(404, f"unknown archetype '{archetype_id}'") from exc
    payload = {
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
    return conditional(payload, settings.cache_ttl_knowledge, if_none_match)


@router.get("/knowledge/channels")
def channels(
    service: ServiceDep,
    settings: SettingsDep,
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
) -> Response:
    payload = [
        {**c.model_dump(), "description": " ".join(c.description.split())}
        for c in service.kb.channels.values()
    ]
    return conditional(payload, settings.cache_ttl_knowledge, if_none_match)


# --------------------------------------------------------------------- events
@router.get("/events")
def events(
    service: ServiceDep,
    repos: ReposDep,
    since: date | None = None,
    until: date | None = None,
    archetype_id: str | None = None,
    limit: int = Query(default=50, le=500),
) -> list[dict]:
    """Persisted events first; the bundled corpus is the fallback for a fresh install."""
    rows = repos.events.between(since, until, archetype_id, limit)
    if rows:
        return [repos.events.to_schema(r).model_dump(mode="json") for r in rows]

    corpus = service.history
    if since:
        corpus = [e for e in corpus if e.event_date >= since]
    if until:
        corpus = [e for e in corpus if e.event_date <= until]
    if archetype_id:
        corpus = [e for e in corpus if e.archetype_id == archetype_id]
    corpus = sorted(corpus, key=lambda e: e.event_date, reverse=True)[:limit]
    return [e.model_dump(mode="json") for e in corpus]


@router.post("/events/classify")
def classify(headline: str, service: ServiceDep) -> list[dict]:
    return [
        {"archetype_id": a, "score": sc, "matched_terms": terms}
        for a, sc, terms in service.classifier.score(headline)[:5]
    ]


# --------------------------------------------------------------------- impact
@router.get("/impact/{event_id}", response_model=list[ImpactScore])
def impact(event_id: str, service: ServiceDep) -> list[ImpactScore]:
    match = [e for e in service.history if e.event_id == event_id]
    if not match:
        raise HTTPException(404, f"unknown event '{event_id}'")
    return service.impact.score_event(match[0])


@router.post("/impact/portfolio")
def portfolio(payload: dict, service: ServiceDep) -> dict:
    """Exposure attribution — which sectors a portfolio's weight sits in.

    Deliberately describes exposure, never action. See §6 of the build brief.
    """
    event_id = payload.get("event_id")
    holdings = payload.get("holdings") or {}
    match = [e for e in service.history if e.event_id == event_id]
    if not match:
        raise HTTPException(404, f"unknown event '{event_id}'")
    out = service.impact.portfolio_exposure(match[0], holdings)
    out["disclaimer"] = DISCLAIMER
    return out


# ---------------------------------------------------------------- event study
@router.get("/eventstudy")
def eventstudy(
    service: ServiceDep,
    symbol: str,
    event_date: date,
    window: str = "T+1..T+5",
) -> dict:
    try:
        parse_window(window)
        return service.study.run(symbol, event_date, window)
    except (ValueError, InsufficientData) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/analogs")
def analogs(
    service: ServiceDep,
    repos: ReposDep,
    settings: SettingsDep,
    archetype_id: str,
    target: str,
    window: str | None = None,
    before: date | None = None,
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
) -> Response:
    """Served from the nightly precompute when possible.

    A cache miss falls back to computing on the fly, which is slow but correct —
    a fresh install with no precompute yet still answers.
    """
    window = window or settings.default_window

    if before is None:
        row = repos.analogs.latest(archetype_id, target, window)
        if row is not None:
            payload = {
                "archetype_id": row.archetype_id,
                "target": row.target,
                "window": row.window,
                "as_of": row.as_of.isoformat(),
                "sample_size": row.sample_size,
                "mean_car_bps": float(row.mean_car_bps),
                "median_car_bps": float(row.median_car_bps),
                "stdev_bps": float(row.stdev_bps),
                "hit_rate": float(row.hit_rate),
                "p5_bps": float(row.p5_bps),
                "p95_bps": float(row.p95_bps),
                "t_stat": float(row.t_stat),
                "p_value": float(row.p_value),
                "analogs": row.analogs or [],
                "precomputed": True,
                "disclaimer": DISCLAIMER,
            }
            return conditional(payload, settings.cache_ttl_analogs, if_none_match)

    try:
        summary = service.analogs.summarise(archetype_id, target, window, before=before)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    if summary is None:
        raise HTTPException(404, "no historical analogs for this archetype/target pair")

    payload = summary.model_dump(mode="json")
    payload["precomputed"] = False
    payload["disclaimer"] = DISCLAIMER
    return conditional(payload, settings.cache_ttl_analogs, if_none_match)


@router.get("/calibration")
def calibration(
    service: ServiceDep,
    repos: ReposDep,
    settings: SettingsDep,
    window: str | None = None,
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
) -> Response:
    """The honesty page: every encoded prior, scored against realised history."""
    window = window or settings.default_window
    run = repos.calibration.latest(window)
    if run is not None:
        payload = {
            "window": window,
            "summary": run.summary,
            "rows": run.rows,
            "run_at": run.run_at.isoformat(),
        }
    else:
        rows = service.analogs.calibration_report(window)
        counts: dict[str, int] = {}
        for r in rows:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        payload = {"window": window, "summary": counts, "rows": rows}
    return conditional(payload, settings.cache_ttl_analogs, if_none_match)


# --------------------------------------------------------------------- alerts
@router.get("/alerts", response_model=list[Alert])
def alerts(
    service: ServiceDep,
    day: date | None = None,
    lookback_days: int = 1,
    min_severity: str = "info",
) -> list[Alert]:
    day = day or service.latest_event_date()
    return service.alerts.build_many(
        service.events_on(day, lookback_days), min_severity=min_severity
    )


@router.get("/digest", response_model=Digest)
def digest(
    service: ServiceDep,
    repos: ReposDep,
    day: date | None = None,
    lookback_days: int = 3,
) -> Digest:
    """Stored digest first — the 07:30 job already built today's."""
    if day is None:
        stored = repos.digests.latest()
        if stored is not None:
            return Digest.model_validate(stored.payload)
        day = service.latest_event_date()
    else:
        stored = repos.digests.get(day)
        if stored is not None:
            return Digest.model_validate(stored.payload)
    return service.digests.build(service.events_on(day, lookback_days), digest_date=day)


@router.get("/digest.md", response_class=Response)
def digest_md(
    service: ServiceDep, day: date | None = None, lookback_days: int = 3
) -> Response:
    day = day or service.latest_event_date()
    text = service.digests.to_markdown(
        service.digests.build(service.events_on(day, lookback_days), digest_date=day)
    )
    return Response(content=text, media_type="text/plain; charset=utf-8")


__all__ = ["router", "conditional"]

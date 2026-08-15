"""FastAPI surface."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from .. import __version__
from ..config import REPO_ROOT
from ..eventstudy.car import InsufficientData, parse_window
from ..explain.guardrails import DISCLAIMER
from ..models import Alert, Digest, Explanation, ImpactScore
from ..service import Impacto, get_service

UI_DIR = REPO_ROOT / "ui"


class HoldingsRequest(BaseModel):
    holdings: dict[str, float]
    event_id: str


def create_app() -> FastAPI:
    app = FastAPI(
        title="Impacto",
        version=__version__,
        description=(
            "Maps global events and policy decisions to Indian equity market impact, "
            "with an auditable transmission map and market-model event studies.\n\n"
            f"**{DISCLAIMER}**"
        ),
    )

    def svc() -> Impacto:
        return get_service()

    # ------------------------------------------------------------- meta
    @app.get("/health", tags=["meta"])
    def health() -> dict:
        s = svc()
        return {
            "status": "ok",
            "version": __version__,
            "market_provider": s.provider.name,
            "knowledge": s.kb.stats(),
            "event_history": len(s.history),
            "compliance_mode": s.settings.compliance_mode,
        }

    @app.get("/knowledge/archetypes", tags=["knowledge"])
    def archetypes() -> list[dict]:
        s = svc()
        return [
            {
                "id": a.id,
                "label": a.label,
                "family": a.family,
                "description": " ".join(a.description.split()),
                "n_impacts": len(a.impacts),
                "targets": [i.target for i in a.impacts],
            }
            for a in s.kb.archetypes.values()
        ]

    @app.get("/knowledge/archetypes/{archetype_id}", tags=["knowledge"])
    def archetype(archetype_id: str) -> dict:
        s = svc()
        try:
            a = s.kb.archetype(archetype_id)
        except KeyError as exc:
            raise HTTPException(404, f"unknown archetype '{archetype_id}'") from exc
        return {
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

    @app.get("/knowledge/channels", tags=["knowledge"])
    def channels() -> list[dict]:
        return [
            {**c.model_dump(), "description": " ".join(c.description.split())}
            for c in svc().kb.channels.values()
        ]

    # ------------------------------------------------------------ events
    @app.get("/events", tags=["events"])
    def events(
        since: date | None = None,
        until: date | None = None,
        archetype_id: str | None = None,
        limit: int = Query(default=50, le=500),
    ) -> list[dict]:
        s = svc()
        rows = s.history
        if since:
            rows = [e for e in rows if e.event_date >= since]
        if until:
            rows = [e for e in rows if e.event_date <= until]
        if archetype_id:
            rows = [e for e in rows if e.archetype_id == archetype_id]
        rows = sorted(rows, key=lambda e: e.event_date, reverse=True)[:limit]
        return [e.model_dump(mode="json") for e in rows]

    @app.post("/events/classify", tags=["events"])
    def classify(headline: str) -> list[dict]:
        s = svc()
        return [
            {"archetype_id": a, "score": sc, "matched_terms": terms}
            for a, sc, terms in s.classifier.score(headline)[:5]
        ]

    # ------------------------------------------------------------ impact
    @app.get("/impact/{event_id}", response_model=list[ImpactScore], tags=["impact"])
    def impact(event_id: str) -> list[ImpactScore]:
        s = svc()
        match = [e for e in s.history if e.event_id == event_id]
        if not match:
            raise HTTPException(404, f"unknown event '{event_id}'")
        return s.impact.score_event(match[0])

    @app.post("/impact/portfolio", tags=["impact"])
    def portfolio(req: HoldingsRequest) -> dict:
        s = svc()
        match = [e for e in s.history if e.event_id == req.event_id]
        if not match:
            raise HTTPException(404, f"unknown event '{req.event_id}'")
        out = s.impact.portfolio_exposure(match[0], req.holdings)
        out["disclaimer"] = DISCLAIMER
        return out

    # ------------------------------------------------------- event study
    @app.get("/eventstudy", tags=["eventstudy"])
    def eventstudy(
        symbol: str,
        event_date: date,
        window: str = "T+1..T+5",
    ) -> dict:
        s = svc()
        try:
            parse_window(window)
            return s.study.run(symbol, event_date, window)
        except (ValueError, InsufficientData) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/analogs", tags=["eventstudy"])
    def analogs(
        archetype_id: str,
        target: str,
        window: str = "T+1..T+5",
        before: date | None = None,
    ) -> dict:
        s = svc()
        try:
            summary = s.analogs.summarise(archetype_id, target, window, before=before)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        if summary is None:
            raise HTTPException(404, "no historical analogs for this archetype/target pair")
        out = summary.model_dump(mode="json")
        out["disclaimer"] = DISCLAIMER
        return out

    @app.get("/calibration", tags=["eventstudy"])
    def calibration(window: str = "T+1..T+5") -> dict:
        s = svc()
        rows = s.analogs.calibration_report(window)
        counts: dict[str, int] = {}
        for r in rows:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        return {"window": window, "summary": counts, "rows": rows}

    # ------------------------------------------------------------ alerts
    @app.get("/alerts", response_model=list[Alert], tags=["alerts"])
    def alerts(
        day: date | None = None,
        lookback_days: int = 1,
        min_severity: str = "info",
    ) -> list[Alert]:
        s = svc()
        day = day or s.latest_event_date()
        return s.alerts.build_many(s.events_on(day, lookback_days), min_severity=min_severity)

    @app.get("/digest", response_model=Digest, tags=["alerts"])
    def digest(day: date | None = None, lookback_days: int = 3) -> Digest:
        s = svc()
        day = day or s.latest_event_date()
        return s.digests.build(s.events_on(day, lookback_days), digest_date=day)

    @app.get("/digest.md", response_class=PlainTextResponse, tags=["alerts"])
    def digest_md(day: date | None = None, lookback_days: int = 3) -> str:
        s = svc()
        day = day or s.latest_event_date()
        return s.digests.to_markdown(
            s.digests.build(s.events_on(day, lookback_days), digest_date=day)
        )

    # ----------------------------------------------------------- explain
    @app.get("/explain", response_model=Explanation, tags=["explain"])
    def explain(
        q: str,
        as_of: date | None = None,
        target: str | None = None,
    ) -> Explanation:
        s = svc()
        return s.explainer.explain(q, as_of=as_of or s.latest_event_date(), target=target)

    # ---------------------------------------------------------------- ui
    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        path: Path = UI_DIR / "index.html"
        if not path.exists():
            raise HTTPException(404, "UI not built")
        return FileResponse(path)

    return app


__all__ = ["create_app"]

"""FastAPI application assembly.

Order matters here. CORS is locked to the configured web origin with no wildcard;
the request-context middleware runs outermost so every log line — including one
from a request that CORS or the rate limiter rejects — carries a request id.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .. import __version__
from ..config import REPO_ROOT, get_settings
from ..db import ping as db_ping
from ..explain.guardrails import DISCLAIMER
from ..jobs import start_scheduler
from ..llm import get_llm
from ..service import get_service
from .cache import get_cache
from .observability import REQUEST_ID_HEADER, RequestContextMiddleware, configure_logging
from .ratelimit import RateLimitExceeded, build_limiter, rate_limit_handler
from .routers import auth, bundle, explain, knowledge, me, push

log = logging.getLogger(__name__)
UI_DIR = REPO_ROOT / "ui"

DESCRIPTION = (
    "Impacto maps global events and policy decisions to Indian equity market "
    "impact, with an auditable transmission map and market-model event studies.\n\n"
    f"**{DISCLAIMER}**"
)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()

    app = FastAPI(title="Impacto", version=__version__, description=DESCRIPTION)

    # --- middleware (added innermost-first; the last added runs first) --------
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        # Exactly one origin. A wildcard here would let any site read an
        # authenticated response, and credentials are in play.
        allow_origins=[settings.web_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "If-None-Match", REQUEST_ID_HEADER],
        expose_headers=["ETag", REQUEST_ID_HEADER, "Retry-After"],
    )
    app.add_middleware(RequestContextMiddleware)

    # --- rate limiting -------------------------------------------------------
    limiter = build_limiter()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

    # --- routes --------------------------------------------------------------
    app.include_router(knowledge.router)
    app.include_router(explain.router)
    app.include_router(bundle.router)
    app.include_router(auth.router)
    app.include_router(me.router)
    app.include_router(push.router)

    # --- probes --------------------------------------------------------------
    @app.get("/health", tags=["meta"])
    def health() -> dict:
        """Liveness only. Must not touch Postgres or Redis: a dependency outage
        should not make the orchestrator kill an otherwise-healthy process."""
        service = get_service()
        return {
            "status": "ok",
            "version": __version__,
            "market_provider": service.provider.name,
            "knowledge": service.kb.stats(),
            "llm_provider": get_llm().name,
            "compliance_mode": service.settings.compliance_mode,
        }

    @app.get("/ready", tags=["meta"])
    def ready() -> JSONResponse:
        """Readiness. Checks the dependencies a request actually needs."""
        cache = get_cache()
        checks = {"database": db_ping(), "cache": cache.ping()}
        ok = all(checks.values())
        return JSONResponse(
            status_code=200 if ok else 503,
            content={"status": "ready" if ok else "degraded", "checks": checks,
                     "cacheBackend": cache.backend},
        )

    @app.get("/", include_in_schema=False)
    def index(request: Request):
        """The legacy single-file dashboard.

        Kept as an operational view for the engine. The PWA in web/ is the product
        surface; this is what you open when debugging the API directly.
        """
        path: Path = UI_DIR / "index.html"
        if not path.exists():
            return JSONResponse({"detail": "UI not built", "docs": "/docs"}, 404)
        return FileResponse(path)

    # --- lifecycle -----------------------------------------------------------
    @app.on_event("startup")
    def _startup() -> None:
        app.state.scheduler = start_scheduler()

    @app.on_event("shutdown")
    def _shutdown() -> None:
        scheduler = getattr(app.state, "scheduler", None)
        if scheduler is not None:
            scheduler.shutdown(wait=False)

    return app


__all__ = ["create_app"]

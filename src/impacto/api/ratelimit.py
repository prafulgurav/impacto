"""Rate limiting — slowapi over Redis, per §2.6.

Three tiers, because the costs differ by an order of magnitude:

  60/min   anonymous      cheap cached reads
  300/min  authenticated  same reads, but we know who is asking
  10/min   /explain/stream  every call can spend LLM tokens

Keyed by user id when authenticated, so one user on a shared mobile NAT cannot
exhaust the quota for everyone behind it.
"""
from __future__ import annotations

import logging

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..config import get_settings

log = logging.getLogger(__name__)


def rate_limit_key(request: Request) -> str:
    """Prefer the authenticated identity; fall back to the client address."""
    user = getattr(request.state, "user_id", None)
    if user:
        return f"user:{user}"
    return f"ip:{get_remote_address(request)}"


def default_limit() -> str:
    """slowapi evaluates this per request, so the tier follows the caller."""
    s = get_settings()
    return f"{s.rate_limit_anonymous}/minute"


def authenticated_limit() -> str:
    return f"{get_settings().rate_limit_authenticated}/minute"


def explain_limit() -> str:
    return f"{get_settings().rate_limit_explain}/minute"


def tiered_limit(request: Request) -> str:
    """One limiter, two tiers, chosen by whether the request carries an identity."""
    return (
        authenticated_limit()
        if getattr(request.state, "user_id", None)
        else default_limit()
    )


def build_limiter() -> Limiter:
    s = get_settings()
    kwargs = {"key_func": rate_limit_key, "default_limits": [tiered_limit]}
    if s.redis_url:
        # Shared counters across replicas. Without this each instance would allow
        # the full quota, so N replicas would mean N times the intended limit.
        kwargs["storage_uri"] = s.redis_url
    limiter = Limiter(**kwargs)
    log.info("rate limiter storage=%s", "redis" if s.redis_url else "memory")
    return limiter


def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """429 with Retry-After, so a client backs off correctly instead of hammering."""
    retry_after = getattr(exc, "retry_after", None) or 60
    return JSONResponse(
        status_code=429,
        content={
            "detail": "rate limit exceeded",
            "limit": str(getattr(exc, "detail", "")),
            "retryAfter": int(retry_after),
        },
        headers={"Retry-After": str(int(retry_after))},
    )


__all__ = [
    "build_limiter",
    "rate_limit_handler",
    "rate_limit_key",
    "tiered_limit",
    "explain_limit",
    "RateLimitExceeded",
]

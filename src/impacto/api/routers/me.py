"""Account-scoped endpoints — /me, watchlist, holdings.

Everything here requires auth and is `no-store`: none of it may be cached by the
service worker, a CDN, or a shared proxy (§5.1).
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator

from ...db.types import MissingEncryptionKey
from ..cache import NO_STORE
from ..deps import CurrentUser, ReposDep

router = APIRouter(prefix="/me", tags=["me"])

MAX_HOLDINGS = 100


class WatchlistUpdate(BaseModel):
    archetype_ids: list[str] = Field(default_factory=list, max_length=50)
    min_severity: str = Field(default="watch")

    @field_validator("min_severity")
    @classmethod
    def _known_severity(cls, v: str) -> str:
        if v not in {"info", "watch", "high"}:
            raise ValueError("min_severity must be info, watch or high")
        return v


class HoldingIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    weight: float = Field(ge=0, le=1)


class HoldingsUpdate(BaseModel):
    holdings: list[HoldingIn] = Field(default_factory=list, max_length=MAX_HOLDINGS)


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = NO_STORE


@router.get("")
def me(user: CurrentUser, repos: ReposDep, response: Response) -> dict:
    _no_store(response)
    watchlist = repos.watchlist.list(user.id)
    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "locale": user.locale,
            "tz": user.tz,
        },
        "watchlist": {
            "archetypeIds": [w.archetype_id for w in watchlist],
            "minSeverity": watchlist[0].min_severity if watchlist else "watch",
        },
        "pushEnabled": bool(repos.push.list(user.id)),
    }


@router.put("/watchlist")
def update_watchlist(
    payload: WatchlistUpdate, user: CurrentUser, repos: ReposDep, response: Response
) -> dict:
    _no_store(response)
    rows = repos.watchlist.replace(user.id, payload.archetype_ids, payload.min_severity)
    return {
        "archetypeIds": [r.archetype_id for r in rows],
        "minSeverity": payload.min_severity,
    }


@router.get("/holdings")
def get_holdings(user: CurrentUser, repos: ReposDep, response: Response) -> dict:
    _no_store(response)
    try:
        rows = repos.holdings.list(user.id, reason="GET /me/holdings")
    except MissingEncryptionKey as exc:
        # The deployment is misconfigured. Say so plainly rather than returning an
        # empty portfolio, which the user would read as data loss.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "holdings storage is not configured on this deployment",
        ) from exc
    return {
        "holdings": [
            {"symbol": r.symbol, "weight": float(r.weight)} for r in rows
        ]
    }


@router.put("/holdings")
def put_holdings(
    payload: HoldingsUpdate, user: CurrentUser, repos: ReposDep, response: Response
) -> dict:
    _no_store(response)
    weights: dict[str, Decimal] = {}
    for item in payload.holdings:
        symbol = item.symbol.strip().upper()
        # Later entries win, matching last-write-wins in the offline outbox.
        weights[symbol] = Decimal(str(item.weight))

    total = sum(weights.values())
    if total > Decimal("1.0001"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"weights sum to {float(total):.4f}; they must not exceed 1.0",
        )

    try:
        rows = repos.holdings.replace(user.id, weights)
    except MissingEncryptionKey as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "holdings storage is not configured on this deployment",
        ) from exc
    return {
        "holdings": [{"symbol": r.symbol, "weight": float(r.weight)} for r in rows]
    }


@router.delete("/holdings", status_code=status.HTTP_204_NO_CONTENT)
def delete_holdings(user: CurrentUser, repos: ReposDep) -> Response:
    repos.holdings.clear(user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]

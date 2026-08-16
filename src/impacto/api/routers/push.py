"""Web Push subscriptions (§2.4).

The payload deliberately carries only `{alertId, archetypeLabel, severity}` and
never a number. Push bodies are not guardrail-checked at send time, and a stale
figure sitting on a lock screen is precisely the misleading-output failure the
whole compliance architecture exists to prevent. The service worker fetches the
full, freshly-checked alert when the notification is tapped.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from ...config import Settings
from ..cache import NO_STORE
from ..deps import CurrentUser, ReposDep, SettingsDep

log = logging.getLogger(__name__)
router = APIRouter(prefix="/push", tags=["push"])

GONE = 410


class SubscriptionKeys(BaseModel):
    p256dh: str = Field(min_length=8)
    auth: str = Field(min_length=8)


class SubscribeRequest(BaseModel):
    endpoint: str = Field(min_length=8, max_length=2048)
    keys: SubscriptionKeys


class UnsubscribeRequest(BaseModel):
    endpoint: str


def build_payload(alert_id: str, archetype_label: str, severity: str) -> dict:
    """The complete push payload. Numbers must never appear here."""
    return {
        "alertId": alert_id,
        "archetypeLabel": archetype_label,
        "severity": severity,
    }


class PushTransport(Protocol):
    """Sends one encrypted push. Injected so the fan-out is testable offline."""

    def send(self, subscription: dict, payload: dict, settings: Settings) -> int: ...


class WebPushTransport:
    """pywebpush-backed transport.

    Constructed lazily and only when VAPID keys are configured, so a deployment
    without push (or without the optional dependency) still starts and serves
    every other endpoint.
    """

    def __init__(self) -> None:
        from pywebpush import webpush  # imported here so the module stays optional

        self._webpush = webpush

    def send(self, subscription: dict, payload: dict, settings: Settings) -> int:
        import json

        response = self._webpush(
            subscription_info=subscription,
            data=json.dumps(payload),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_subject},
        )
        return getattr(response, "status_code", 201)


def get_transport(settings: Settings) -> PushTransport | None:
    if not (settings.vapid_private_key and settings.vapid_public_key):
        return None
    try:
        return WebPushTransport()
    except ImportError:
        log.warning("pywebpush is not installed; push sending is disabled")
        return None


def fan_out(
    repos,
    settings: Settings,
    endpoints: list[dict],
    payload: dict,
    transport: PushTransport | None = None,
) -> dict[str, Any]:
    """Send one payload to many endpoints, pruning the dead ones.

    A 410 Gone means the browser discarded the subscription; three in a row and we
    stop carrying it (§2.4). Any other failure is transient and left alone.
    """
    transport = transport or get_transport(settings)
    result = {"sent": 0, "failed": 0, "pruned": 0, "skipped": len(endpoints)}
    if transport is None:
        return result

    result["skipped"] = 0
    for subscription in endpoints:
        endpoint = subscription["endpoint"]
        try:
            code = transport.send(subscription, payload, settings)
        except Exception as exc:
            code = getattr(getattr(exc, "response", None), "status_code", 0)
            log.info("push send failed for %s: %s", endpoint[:40], exc)

        if code == GONE:
            if repos.push.record_failure(endpoint):
                result["pruned"] += 1
            result["failed"] += 1
        elif 200 <= code < 300:
            repos.push.record_success(endpoint)
            result["sent"] += 1
        else:
            result["failed"] += 1
    return result


@router.get("/public-key")
def public_key(settings: SettingsDep) -> dict:
    """The VAPID public key the browser needs to create a subscription."""
    if not settings.vapid_public_key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "push is not configured"
        )
    return {"publicKey": settings.vapid_public_key}


@router.post("/subscribe", status_code=status.HTTP_201_CREATED)
def subscribe(
    payload: SubscribeRequest,
    user: CurrentUser,
    repos: ReposDep,
    response: Response,
) -> dict:
    response.headers["Cache-Control"] = NO_STORE
    row = repos.push.subscribe(
        user_id=user.id,
        endpoint=payload.endpoint,
        p256dh=payload.keys.p256dh,
        auth=payload.keys.auth,
    )
    return {"id": str(row.id), "endpoint": row.endpoint}


@router.delete("/subscribe", status_code=status.HTTP_204_NO_CONTENT)
def unsubscribe(
    payload: UnsubscribeRequest, user: CurrentUser, repos: ReposDep
) -> Response:
    repos.push.unsubscribe(payload.endpoint)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router", "build_payload", "fan_out", "get_transport", "WebPushTransport"]

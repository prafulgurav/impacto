"""Phase 2 acceptance: auth, SSE, caching, the offline bundle and CORS.

The properties pinned here are the ones that are invisible when they break: an
endpoint that quietly stops requiring auth, a `composed` event that stops arriving
first, or an explanation that starts being cached.
"""
from __future__ import annotations

import gzip
import json

import pytest

from conftest import TEST_JWT_SECRET, WEB_ORIGIN
from impacto.api.cache import compute_etag, etag_matches
from impacto.api.routers.bundle import CACHE_KEY, build_bundle
from impacto.api.routers.push import build_payload, fan_out
from impacto.api.security import (
    AuthError,
    decode_access_token,
    issue_access_token,
    issue_magic_token,
    verify_magic_token,
)
from impacto.config import Settings


@pytest.fixture()
def authed(client):
    """A signed-in client. Magic link is the path that needs no external service."""
    token = issue_magic_token("reader@example.com", Settings(jwt_secret=TEST_JWT_SECRET))
    response = client.post("/auth/verify", json={"token": token})
    assert response.status_code == 200, response.text
    access = response.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {access}"})
    return client


# ------------------------------------------------------------------- tokens
def test_access_token_round_trips():
    settings = Settings(jwt_secret="s" * 32)
    token, expires_in = issue_access_token("u-1", "a@b.com", settings)
    claims = decode_access_token(token, settings)
    assert claims.user_id == "u-1"
    assert claims.email == "a@b.com"
    assert expires_in == settings.access_token_minutes * 60


def test_a_token_signed_with_another_secret_is_rejected():
    token, _ = issue_access_token("u-1", "a@b.com", Settings(jwt_secret="secret-one"))
    with pytest.raises(AuthError):
        decode_access_token(token, Settings(jwt_secret="secret-two"))


def test_missing_jwt_secret_fails_closed():
    """A default signing key is indistinguishable from having no auth at all."""
    with pytest.raises(AuthError):
        issue_access_token("u", "a@b.com", Settings(jwt_secret=None))


def test_magic_token_carries_a_normalised_email():
    settings = Settings(jwt_secret="s" * 32)
    assert verify_magic_token(issue_magic_token("  A@B.COM ", settings), settings) == "a@b.com"


def test_an_access_token_cannot_be_used_as_a_magic_token():
    """Audience separation: the two token kinds must not be interchangeable."""
    settings = Settings(jwt_secret="s" * 32)
    access, _ = issue_access_token("u-1", "a@b.com", settings)
    with pytest.raises(AuthError):
        verify_magic_token(access, settings)


# --------------------------------------------------------------- auth flow
def test_magic_link_never_reveals_whether_an_account_exists(client):
    known = client.post("/auth/magic-link", json={"email": "reader@example.com"})
    unknown = client.post("/auth/magic-link", json={"email": "nobody@example.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.json()["sent"] == unknown.json()["sent"] is True


def test_full_sign_in_refresh_and_logout_cycle(client):
    token = issue_magic_token("reader@example.com", Settings(jwt_secret=TEST_JWT_SECRET))
    signed_in = client.post("/auth/verify", json={"token": token})
    assert signed_in.status_code == 200
    body = signed_in.json()
    assert body["user"]["email"] == "reader@example.com"
    assert client.cookies.get("impacto_refresh")

    client.headers.update({"Authorization": f"Bearer {body['access_token']}"})
    assert client.get("/me").status_code == 200

    before = client.cookies.get("impacto_refresh")
    refreshed = client.post("/auth/refresh")
    assert refreshed.status_code == 200
    # The refresh token is what must rotate. Two access tokens minted in the same
    # second carry identical claims and so are byte-identical — that is expected,
    # not a defect, since they expire together anyway.
    assert client.cookies.get("impacto_refresh") != before
    assert refreshed.json()["user"]["email"] == "reader@example.com"

    assert client.post("/auth/logout").status_code == 204
    assert client.post("/auth/refresh").status_code == 401


def test_refresh_tokens_rotate_so_a_stolen_cookie_dies(client):
    token = issue_magic_token("reader@example.com", Settings(jwt_secret=TEST_JWT_SECRET))
    client.post("/auth/verify", json={"token": token})
    stolen = client.cookies.get("impacto_refresh")

    assert client.post("/auth/refresh").status_code == 200

    # The attacker replays the cookie they captured before the legitimate refresh.
    client.cookies.set("impacto_refresh", stolen)
    assert client.post("/auth/refresh").status_code == 401


def test_refresh_cookie_is_httponly_and_samesite_lax(client):
    token = issue_magic_token("reader@example.com", Settings(jwt_secret=TEST_JWT_SECRET))
    response = client.post("/auth/verify", json={"token": token})
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "path=/" in cookie


def test_an_invalid_magic_link_is_rejected(client):
    assert client.post("/auth/verify", json={"token": "n" * 40}).status_code == 401


# ------------------------------------------------------------ anonymous access
@pytest.mark.parametrize(
    "path",
    [
        "/knowledge/archetypes",
        "/knowledge/channels",
        "/events",
        "/calibration",
        "/digest",
        "/bundle/offline",
        "/explain?q=why+did+IT+stocks+move",
    ],
)
def test_public_surface_stays_open_to_anonymous_callers(client, path):
    """Gating these would close the SEO and LLM-citation acquisition channel."""
    assert client.get(path).status_code == 200


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/me"),
        ("put", "/me/watchlist"),
        ("get", "/me/holdings"),
        ("put", "/me/holdings"),
        ("post", "/push/subscribe"),
    ],
)
def test_account_endpoints_require_auth(client, method, path):
    kwargs = {} if method == "get" else {"json": {}}
    response = getattr(client, method)(path, **kwargs)
    assert response.status_code == 401


def test_an_expired_or_bogus_token_is_treated_as_anonymous(client):
    """A stale token must degrade to the public site, not to an error page."""
    client.headers.update({"Authorization": "Bearer not-a-real-token"})
    assert client.get("/knowledge/archetypes").status_code == 200
    assert client.get("/me").status_code == 401


# ------------------------------------------------------------------ watchlist
def test_watchlist_round_trips(authed):
    response = authed.put(
        "/me/watchlist",
        json={"archetype_ids": ["FED_HAWKISH_SURPRISE", "GOLD_SPIKE"], "min_severity": "high"},
    )
    assert response.status_code == 200
    assert response.json()["archetypeIds"] == ["FED_HAWKISH_SURPRISE", "GOLD_SPIKE"]
    assert authed.get("/me").json()["watchlist"]["minSeverity"] == "high"


def test_watchlist_rejects_an_unknown_severity(authed):
    response = authed.put("/me/watchlist", json={"archetype_ids": [], "min_severity": "urgent"})
    assert response.status_code == 422


# ------------------------------------------------------------------- holdings
def test_holdings_round_trip_and_are_never_cached(authed):
    response = authed.put(
        "/me/holdings",
        json={"holdings": [{"symbol": "tcs", "weight": 0.4}, {"symbol": "INFY", "weight": 0.3}]},
    )
    assert response.status_code == 200
    assert response.headers["cache-control"].startswith("no-store")
    assert {h["symbol"] for h in response.json()["holdings"]} == {"TCS", "INFY"}

    assert {h["symbol"] for h in authed.get("/me/holdings").json()["holdings"]} == {"TCS", "INFY"}


def test_holdings_over_one_hundred_percent_are_rejected(authed):
    response = authed.put(
        "/me/holdings",
        json={"holdings": [{"symbol": "A", "weight": 0.7}, {"symbol": "B", "weight": 0.7}]},
    )
    assert response.status_code == 422


def test_reading_holdings_through_the_api_leaves_an_audit_trail(authed, db):
    authed.put("/me/holdings", json={"holdings": [{"symbol": "TCS", "weight": 0.5}]})
    authed.get("/me/holdings")
    assert db.audit.recent(kind="holdings_access", limit=10)


# ----------------------------------------------------------------------- push
def test_push_payload_carries_no_numbers():
    """A stale figure on a lock screen is the exact failure the guardrail prevents."""
    payload = build_payload("alert-1", "Fed hawkish surprise", "high")
    assert set(payload) == {"alertId", "archetypeLabel", "severity"}
    serialised = json.dumps(payload)
    assert not any(ch.isdigit() for ch in payload["archetypeLabel"])
    assert "bps" not in serialised


def test_push_subscribe_and_unsubscribe(authed):
    body = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "k" * 16, "auth": "a" * 16}}
    assert authed.post("/push/subscribe", json=body).status_code == 201
    assert authed.get("/me").json()["pushEnabled"] is True

    assert authed.request("DELETE", "/push/subscribe", json={"endpoint": body["endpoint"]}).status_code == 204
    assert authed.get("/me").json()["pushEnabled"] is False


def test_fan_out_prunes_a_subscription_after_three_gone_responses(db, user):
    class AlwaysGone:
        def send(self, subscription, payload, settings):
            return 410

    endpoint = "https://push.example/dead"
    db.push.subscribe(user.id, endpoint, "p" * 16, "a" * 16)
    db.flush()

    subscription = {"endpoint": endpoint, "keys": {"p256dh": "p", "auth": "a"}}
    settings = Settings(vapid_public_key="pub", vapid_private_key="priv")
    for _ in range(2):
        assert fan_out(db, settings, [subscription], {}, AlwaysGone())["pruned"] == 0
    assert fan_out(db, settings, [subscription], {}, AlwaysGone())["pruned"] == 1
    db.flush()
    assert db.push.list(user.id) == []


def test_fan_out_is_a_no_op_without_vapid_keys(db):
    result = fan_out(db, Settings(), [{"endpoint": "https://x"}], {})
    assert result == {"sent": 0, "failed": 0, "pruned": 0, "skipped": 1}


# ------------------------------------------------------------------ etags
def test_etag_is_stable_across_key_ordering():
    assert compute_etag({"a": 1, "b": 2}) == compute_etag({"b": 2, "a": 1})


def test_if_none_match_handles_lists_wildcards_and_weak_tags():
    etag = compute_etag({"a": 1})
    assert etag_matches(etag, etag)
    assert etag_matches(f'"other", {etag}', etag)
    assert etag_matches("*", etag)
    assert etag_matches(f"W/{etag}", etag)
    assert not etag_matches('"nope"', etag)
    assert not etag_matches(None, etag)


@pytest.mark.parametrize(
    "path", ["/knowledge/archetypes", "/knowledge/channels", "/calibration"]
)
def test_public_reads_answer_304_on_a_matching_etag(client, path):
    first = client.get(path)
    assert first.status_code == 200
    etag = first.headers["etag"]

    second = client.get(path, headers={"If-None-Match": etag})
    assert second.status_code == 304
    assert second.content == b""


def test_public_reads_carry_a_cache_control_ttl(client):
    response = client.get("/knowledge/archetypes")
    assert "max-age=" in response.headers["cache-control"]
    assert "stale-while-revalidate=" in response.headers["cache-control"]


# ---------------------------------------------------------------- the bundle
def test_bundle_answers_304_on_a_match(client):
    first = client.get("/bundle/offline")
    assert first.status_code == 200
    second = client.get("/bundle/offline", headers={"If-None-Match": first.headers["etag"]})
    assert second.status_code == 304


def test_bundle_contains_everything_a_cold_launch_needs(client):
    payload = client.get("/bundle/offline").json()
    assert set(payload) >= {
        "generatedAt",
        "archetypes",
        "channels",
        "analogSummaries",
        "digest",
        "recentEvents",
        "disclaimer",
        "defaultWindow",
    }
    assert payload["archetypes"], "the transmission map must ship in the bundle"
    assert payload["disclaimer"]


def test_bundle_stays_within_its_gzipped_budget(client):
    """Acceptance (§9, Phase 2): under 300 KB gzipped."""
    response = client.get("/bundle/offline")
    gzipped = len(gzip.compress(response.content, compresslevel=6))
    assert gzipped < 300 * 1024, f"{gzipped} bytes gzipped"


def test_bundle_sheds_analog_detail_rather_than_blowing_the_budget(service, db):
    """When the payload is too big, detail is dropped and the client is told."""
    tiny = Settings(bundle_max_bytes=1)
    bundle = build_bundle(service, db, tiny)
    assert bundle["analogDetailOmitted"] is True
    assert all(row["analogs"] == [] for row in bundle["analogSummaries"])


def test_bundle_is_cached_between_requests(client):
    from impacto.api.cache import get_cache

    client.get("/bundle/offline")
    assert get_cache().get_json(CACHE_KEY) is not None


# ------------------------------------------------------------------- explain
def test_explain_is_never_cached(client):
    """A stale explanation attached to today's move is the failure mode to avoid."""
    response = client.get("/explain?q=why+did+IT+stocks+fall")
    assert response.headers["cache-control"].startswith("no-store")


def test_explain_writes_an_audit_row(client, db):
    client.get("/explain?q=why+did+IT+stocks+fall")
    rows = db.audit.recent(kind="explain", limit=5)
    assert rows
    assert rows[0].answer


def _sse_events(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        name = data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if name:
            events.append((name, data))
    return events


def test_stream_emits_composed_before_anything_else(client):
    response = client.get("/explain/stream?q=why+did+IT+stocks+fall")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = _sse_events(response.text)
    assert events[0][0] == "composed"
    assert events[0][1]["answer"].strip()
    assert events[-1][0] == "done"


def test_stream_composed_answer_is_complete_on_its_own(client):
    """With no LLM configured the composed answer is the whole product."""
    events = dict(_sse_events(client.get("/explain/stream?q=why+did+IT+stocks+fall").text))
    assert events["composed"]["answer"] == events["done"]["answer"]
    assert events["done"]["usedLlm"] is False


def test_stream_returns_an_audit_id_for_the_rendered_beacon(client, db):
    events = dict(_sse_events(client.get("/explain/stream?q=why+did+IT+stocks+fall").text))
    audit_id = events["done"]["auditId"]
    assert audit_id

    assert client.post("/explain/rendered", json={"auditId": audit_id}).status_code == 202
    assert db.audit.recent(kind="rendered", limit=5)


def test_stream_is_not_cacheable(client):
    response = client.get("/explain/stream?q=why+did+IT+stocks+fall")
    assert response.headers["cache-control"].startswith("no-store")
    # Without this an intermediary buffers the stream and `composed` loses its point.
    assert response.headers["x-accel-buffering"] == "no"


# ---------------------------------------------------------------- cors, probes
def test_cors_allows_the_configured_origin_only(client):
    allowed = client.options(
        "/knowledge/archetypes",
        headers={"Origin": WEB_ORIGIN, "Access-Control-Request-Method": "GET"},
    )
    assert allowed.headers.get("access-control-allow-origin") == WEB_ORIGIN

    denied = client.options(
        "/knowledge/archetypes",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert denied.headers.get("access-control-allow-origin") != "https://evil.example"


def test_no_wildcard_origin_is_ever_returned(client):
    response = client.get("/knowledge/archetypes", headers={"Origin": WEB_ORIGIN})
    assert response.headers.get("access-control-allow-origin") != "*"


def test_health_is_liveness_only_and_ready_checks_dependencies(client):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    ready = client.get("/ready")
    assert ready.status_code == 200
    assert set(ready.json()["checks"]) == {"database", "cache"}


def test_every_response_echoes_a_request_id(client):
    assert client.get("/health").headers["X-Request-Id"]


def test_an_upstream_request_id_is_preserved(client):
    """A trace has to survive the hop from the web tier."""
    response = client.get("/health", headers={"X-Request-Id": "trace-abc-123"})
    assert response.headers["X-Request-Id"] == "trace-abc-123"


def test_openapi_schema_is_valid(client):
    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    body = schema.json()
    assert body["info"]["title"] == "Impacto"
    for path in ("/auth/google", "/auth/refresh", "/me", "/bundle/offline", "/explain/stream"):
        assert path in body["paths"], f"{path} missing from the OpenAPI schema"

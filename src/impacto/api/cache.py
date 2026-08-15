"""Response cache and ETags.

Redis when configured, an in-process LRU otherwise, so a clone runs with no
services and a deployment gets a shared cache by changing one env var.

The TTLs mirror the service-worker strategy table in CLAUDE.md. That symmetry is the
point: the SW revalidates cheaply with `If-None-Match`, and the server answers 304
without recomputing — which is what makes a repeat launch on a slow connection feel
instant.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections import OrderedDict
from typing import Any

from ..config import get_settings

log = logging.getLogger(__name__)

_MEMORY_MAX_ENTRIES = 512


class _MemoryCache:
    """Bounded LRU. Adequate for single-instance dev; not shared between replicas."""

    def __init__(self, maxsize: int = _MEMORY_MAX_ENTRIES) -> None:
        self._data: OrderedDict[str, str] = OrderedDict()
        self._maxsize = maxsize

    def get(self, key: str) -> str | None:
        if key not in self._data:
            return None
        self._data.move_to_end(key)
        return self._data[key]

    def setex(self, key: str, _ttl: int, value: str) -> None:
        # TTL is ignored deliberately: entries are evicted by capacity instead.
        # Every cached payload here is regenerable, so serving a slightly stale
        # dev response is preferable to the complexity of expiry bookkeeping.
        self._data[key] = value
        self._data.move_to_end(key)
        while len(self._data) > self._maxsize:
            self._data.popitem(last=False)

    def delete(self, *keys: str) -> None:
        for key in keys:
            self._data.pop(key, None)

    def flushdb(self) -> None:
        self._data.clear()

    def ping(self) -> bool:
        return True


class ResponseCache:
    def __init__(self, client: Any | None = None) -> None:
        self._client = client if client is not None else _build_client()

    @property
    def backend(self) -> str:
        return "memory" if isinstance(self._client, _MemoryCache) else "redis"

    def get_json(self, key: str) -> Any | None:
        try:
            raw = self._client.get(key)
        except Exception as exc:  # a cache outage must never fail a request
            log.warning("cache read failed for %s: %s", key, exc)
            return None
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def set_json(self, key: str, value: Any, ttl: int) -> None:
        try:
            self._client.setex(key, ttl, json.dumps(value, separators=(",", ":")))
        except Exception as exc:
            log.warning("cache write failed for %s: %s", key, exc)

    def invalidate(self, *keys: str) -> None:
        try:
            self._client.delete(*keys)
        except Exception as exc:
            log.warning("cache invalidate failed: %s", exc)

    def clear(self) -> None:
        try:
            self._client.flushdb()
        except Exception:
            pass

    def ping(self) -> bool:
        """Used by /ready. In-memory always answers True — there is nothing to fail."""
        try:
            return bool(self._client.ping())
        except Exception:
            return False


def _build_client() -> Any:
    url = get_settings().redis_url
    if not url:
        return _MemoryCache()
    try:
        import redis

        client = redis.Redis.from_url(url, decode_responses=True)
        client.ping()
        return client
    except Exception as exc:
        # A missing Redis degrades to local caching rather than taking the API down.
        log.warning("redis unavailable (%s); falling back to in-memory cache", exc)
        return _MemoryCache()


_cache: ResponseCache | None = None


def get_cache() -> ResponseCache:
    global _cache
    if _cache is None:
        _cache = ResponseCache()
    return _cache


def reset_cache() -> None:
    global _cache
    _cache = None


# --------------------------------------------------------------------- etag
def compute_etag(payload: Any) -> str:
    """A strong ETag over the canonical JSON form.

    Sorted keys so an identical payload always hashes identically — otherwise dict
    ordering would defeat every conditional request.
    """
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return '"' + hashlib.sha256(body.encode()).hexdigest()[:32] + '"'


def etag_matches(if_none_match: str | None, etag: str) -> bool:
    """RFC 9110 If-None-Match: a comma-separated list, `*`, or weak-prefixed tags."""
    if not if_none_match:
        return False
    candidates = [c.strip() for c in if_none_match.split(",")]
    if "*" in candidates:
        return True
    return any(c.removeprefix("W/") == etag.removeprefix("W/") for c in candidates)


def cache_control(ttl: int, public: bool = True) -> str:
    scope = "public" if public else "private"
    # stale-while-revalidate lets the service worker paint instantly and refresh in
    # the background — the "no spinner on a warm launch" requirement (§5.2).
    return f"{scope}, max-age={ttl}, stale-while-revalidate={ttl // 2}"


NO_STORE = "no-store, no-cache, must-revalidate, private"

__all__ = [
    "ResponseCache",
    "get_cache",
    "reset_cache",
    "compute_etag",
    "etag_matches",
    "cache_control",
    "NO_STORE",
]

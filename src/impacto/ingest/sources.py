"""News and event sources.

Only the fixture source is exercised in tests/CI — network sources are opt-in so
the test suite is hermetic and the demo works on a plane.
"""
from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from datetime import UTC, date, datetime
from pathlib import Path

from ..config import get_settings
from ..models import DetectedEvent, NewsItem


def _mk_id(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


class NewsSource(ABC):
    name: str = "abstract"

    @abstractmethod
    def fetch(self, since: date, until: date | None = None) -> list[NewsItem]: ...


# ---------------------------------------------------------------------------
class FixtureNewsSource(NewsSource):
    """Bundled headline corpus. Deterministic, offline, used by tests and demo."""

    name = "fixture"

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self.dir = Path(fixtures_dir or get_settings().fixtures_dir)

    def fetch(self, since: date, until: date | None = None) -> list[NewsItem]:
        raw = json.loads((self.dir / "headlines.json").read_text())
        until = until or date.today()
        out: list[NewsItem] = []
        for r in raw:
            ts = datetime.fromisoformat(r["published_at"])
            if since <= ts.date() <= until:
                out.append(
                    NewsItem(
                        id=_mk_id(r["title"], r["published_at"]),
                        published_at=ts,
                        title=r["title"],
                        url=r.get("url"),
                        source=r.get("source", "fixture"),
                        summary=r.get("summary"),
                    )
                )
        return sorted(out, key=lambda i: i.published_at)


# ---------------------------------------------------------------------------
class RSSSource(NewsSource):
    """Indian financial media RSS (Moneycontrol, ET Markets, Mint).

    feedparser is an optional dependency; the source degrades to an empty list
    rather than crashing the pipeline if it is absent.
    """

    name = "rss"

    def __init__(self, feeds: list[str] | None = None) -> None:
        self.feeds = feeds or get_settings().rss_feed_list

    def fetch(self, since: date, until: date | None = None) -> list[NewsItem]:  # pragma: no cover
        try:
            import feedparser
        except ImportError:
            return []
        until = until or date.today()
        out: list[NewsItem] = []
        for url in self.feeds:
            parsed = feedparser.parse(url)
            source = parsed.feed.get("title", url)
            for entry in parsed.entries:
                struct = entry.get("published_parsed") or entry.get("updated_parsed")
                if not struct:
                    continue
                ts = datetime(*struct[:6], tzinfo=UTC)
                if not (since <= ts.date() <= until):
                    continue
                out.append(
                    NewsItem(
                        id=_mk_id(entry.get("title", ""), ts.isoformat()),
                        published_at=ts,
                        title=entry.get("title", ""),
                        url=entry.get("link"),
                        source=source,
                        summary=(entry.get("summary") or "")[:600],
                    )
                )
        return sorted(out, key=lambda i: i.published_at)


# ---------------------------------------------------------------------------
class GDELTSource(NewsSource):
    """GDELT 2.0 DOC API — global event coverage, free, updated every 15 minutes.

    Chosen over NewsAPI/Marketaux because it is free at production volume and
    covers non-Anglophone sources, which matters for OPEC/China/Gulf events that
    Indian media picks up late.
    """

    name = "gdelt"
    ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"

    def __init__(self, query: str | None = None, max_records: int = 200) -> None:
        self.query = query or (
            '(fomc OR "federal reserve" OR opec OR tariff OR "export control" '
            'OR "china stimulus" OR sanctions) sourcelang:eng'
        )
        self.max_records = max_records

    def fetch(self, since: date, until: date | None = None) -> list[NewsItem]:  # pragma: no cover
        import httpx

        until = until or date.today()
        params = {
            "query": self.query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": str(self.max_records),
            "startdatetime": since.strftime("%Y%m%d") + "000000",
            "enddatetime": until.strftime("%Y%m%d") + "235959",
        }
        try:
            resp = httpx.get(self.ENDPOINT, params=params, timeout=30.0)
            resp.raise_for_status()
            articles = resp.json().get("articles", [])
        except Exception:
            return []
        out: list[NewsItem] = []
        for a in articles:
            try:
                ts = datetime.strptime(a["seendate"], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
            except (KeyError, ValueError):
                continue
            out.append(
                NewsItem(
                    id=_mk_id(a.get("title", ""), a.get("seendate", "")),
                    published_at=ts,
                    title=a.get("title", ""),
                    url=a.get("url"),
                    source=a.get("domain", "gdelt"),
                )
            )
        return sorted(out, key=lambda i: i.published_at)


# ---------------------------------------------------------------------------
def load_event_history(fixtures_dir: Path | None = None) -> list[DetectedEvent]:
    """Curated historical event log used as the analog corpus."""
    d = Path(fixtures_dir or get_settings().fixtures_dir)
    raw = json.loads((d / "events.json").read_text())
    return [
        DetectedEvent(
            event_id=r["event_id"],
            archetype_id=r["archetype_id"],
            event_date=date.fromisoformat(r["event_date"]),
            headline=r["headline"],
            sources=r.get("sources", []),
            match_score=r.get("match_score", 1.0),
            surprise_magnitude=r.get("surprise_magnitude"),
            notes=r.get("notes"),
        )
        for r in raw
    ]


__all__ = [
    "NewsSource",
    "FixtureNewsSource",
    "RSSSource",
    "GDELTSource",
    "load_event_history",
]

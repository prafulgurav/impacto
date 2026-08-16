"""Engine and session lifecycle.

Nothing outside `impacto.db` should import SQLAlchemy. Callers get a `Repositories`
bundle from `session_scope()` and never touch a Session or raw SQL — which keeps the
audit obligations on holdings and generated text enforceable in one place.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ..config import get_settings
from .models import Base


def _is_memory_sqlite(url: str) -> bool:
    return url.startswith("sqlite") and (":memory:" in url or url in ("sqlite://",))


def _connect_args(url: str) -> dict:
    # SQLite is the test and local-dev backend; the default thread check would break
    # the TestClient, which runs the app on a different thread to the test.
    return {"check_same_thread": False} if url.startswith("sqlite") else {}


def build_engine(url: str | None = None, echo: bool = False) -> Engine:
    url = url or get_settings().database_url
    kwargs: dict = {
        "echo": echo,
        "future": True,
        "pool_pre_ping": not url.startswith("sqlite"),
        "connect_args": _connect_args(url),
    }
    if _is_memory_sqlite(url):
        # An in-memory SQLite database lives inside its connection. The default pool
        # hands each thread a fresh connection, so the app thread would see an empty
        # schema while the test thread sees the tables. StaticPool shares one.
        kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        # SQLite ignores foreign keys unless asked; without this the cascade
        # behaviour under test would not match Postgres.
        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_connection, _record):  # pragma: no cover - trivial
            cur = dbapi_connection.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return build_engine()


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


def reset_engine_cache() -> None:
    """Used by tests, and after any runtime change to the database URL."""
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


def create_all(engine: Engine | None = None) -> None:
    """Create the schema directly.

    For tests and throwaway local databases only — a real deployment goes through
    `alembic upgrade head` so the migration path itself is exercised.
    """
    Base.metadata.create_all(engine or get_engine())


@contextmanager
def session_scope(factory: sessionmaker[Session] | None = None) -> Iterator[Session]:
    """A transactional scope. Commits on success, rolls back on any exception."""
    session = (factory or get_sessionmaker())()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ping(engine: Engine | None = None) -> bool:
    """Used by /ready. Returns False rather than raising so the probe can report."""
    from sqlalchemy import text

    try:
        with (engine or get_engine()).connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


__all__ = [
    "build_engine",
    "get_engine",
    "get_sessionmaker",
    "reset_engine_cache",
    "create_all",
    "session_scope",
    "ping",
]

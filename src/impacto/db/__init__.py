"""Persistence. The only module in the app that imports SQLAlchemy.

Callers use `repositories()` for a transactional scope and never see a Session:

    with repositories() as repos:
        repos.events.upsert_many(events)
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session, sessionmaker

from .models import Base
from .repositories import HoldingRecord, Repositories, hash_ip, hash_token
from .session import (
    build_engine,
    create_all,
    get_engine,
    get_sessionmaker,
    ping,
    reset_engine_cache,
    session_scope,
)
from .types import MissingEncryptionKey, generate_encryption_key


@contextmanager
def repositories(factory: sessionmaker[Session] | None = None) -> Iterator[Repositories]:
    """A transactional repository bundle. Commits on success, rolls back on error."""
    with session_scope(factory) as session:
        yield Repositories(session)


__all__ = [
    "Base",
    "Repositories",
    "HoldingRecord",
    "repositories",
    "session_scope",
    "build_engine",
    "get_engine",
    "get_sessionmaker",
    "reset_engine_cache",
    "create_all",
    "ping",
    "hash_token",
    "hash_ip",
    "MissingEncryptionKey",
    "generate_encryption_key",
]

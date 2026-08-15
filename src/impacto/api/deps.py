"""FastAPI dependencies.

Authentication is *optional* almost everywhere. Anonymous browsing has to keep
working for every knowledge, event, analog, calibration, digest and explain
endpoint — those pages are the SEO and LLM-citation surface, which is the
acquisition channel (§2.3). Auth gates only /me/*, /push/* and portfolio.
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status

from ..config import Settings, get_settings
from ..db import Repositories, session_scope
from ..db.models import User
from ..service import Impacto, get_service
from .security import AuthError, decode_access_token


def settings_dep() -> Settings:
    return get_settings()


def service_dep() -> Impacto:
    return get_service()


def repos_dep() -> Iterator[Repositories]:
    """One transaction per request. Commits on a clean response, rolls back on error."""
    with session_scope() as session:
        yield Repositories(session)


SettingsDep = Annotated[Settings, Depends(settings_dep)]
ServiceDep = Annotated[Impacto, Depends(service_dep)]
ReposDep = Annotated[Repositories, Depends(repos_dep)]


def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def optional_user(
    request: Request,
    repos: ReposDep,
    authorization: Annotated[str | None, Header()] = None,
) -> User | None:
    """Resolve the caller if a valid token is present; never reject.

    A bad or expired token is treated exactly like no token, so an anonymous
    browser with stale credentials still sees the public site rather than a 401.
    """
    token = _bearer(authorization)
    if not token:
        return None
    try:
        claims = decode_access_token(token)
        user = repos.users.get(UUID(claims.user_id))
    except (AuthError, ValueError):
        return None
    if user is not None:
        # Read by the rate limiter to pick the authenticated tier.
        request.state.user_id = str(user.id)
    return user


def require_user(
    user: Annotated[User | None, Depends(optional_user)],
) -> User:
    """Gate for /me/*, /push/* and portfolio."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="sign in required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


OptionalUser = Annotated[User | None, Depends(optional_user)]
CurrentUser = Annotated[User, Depends(require_user)]


def client_ip(request: Request) -> str | None:
    """The originating address, trusting the proxy's first X-Forwarded-For entry.

    Only ever stored hashed (see db.repositories.hash_ip), so this is used for
    session-anomaly detection rather than identification.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


__all__ = [
    "SettingsDep",
    "ServiceDep",
    "ReposDep",
    "OptionalUser",
    "CurrentUser",
    "optional_user",
    "require_user",
    "client_ip",
    "repos_dep",
]

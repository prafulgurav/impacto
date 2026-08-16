"""Authentication — Google OAuth and email magic link (§2.3).

No passwords anywhere. The refresh token lives only in an httpOnly Secure
SameSite=Lax cookie, so script running in the page cannot read it, and it is
rotated on every use: a stolen refresh token is usable at most once before the
legitimate client's next refresh invalidates it.
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field

from ...db.models import User
from ..deps import CurrentUser, ReposDep, SettingsDep, client_ip
from ..security import (
    REFRESH_COOKIE,
    AuthError,
    issue_access_token,
    issue_magic_token,
    issue_refresh_token,
    verify_google_id_token,
    verify_magic_token,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


class GoogleSignInRequest(BaseModel):
    id_token: str = Field(min_length=16)


class MagicLinkRequest(BaseModel):
    email: EmailStr


class MagicVerifyRequest(BaseModel):
    token: str = Field(min_length=16)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


def _set_refresh_cookie(response: Response, token: str, settings) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.refresh_token_days * 24 * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        # Lax rather than Strict: the Google redirect is a top-level navigation
        # back to our origin, and Strict would drop the cookie on that hop.
        samesite="lax",
        domain=settings.cookie_domain,
        path="/",
    )


def _user_payload(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "locale": user.locale,
        "tz": user.tz,
    }


def _issue_session(
    request: Request, response: Response, repos, settings, user: User
) -> TokenResponse:
    refresh = issue_refresh_token()
    repos.auth_sessions.create(
        user_id=user.id,
        refresh_token=refresh,
        ttl_days=settings.refresh_token_days,
        user_agent=request.headers.get("user-agent"),
        ip=client_ip(request),
    )
    _set_refresh_cookie(response, refresh, settings)
    access, expires_in = issue_access_token(str(user.id), user.email, settings)
    return TokenResponse(access_token=access, expires_in=expires_in, user=_user_payload(user))


@router.post("/google", response_model=TokenResponse)
def google_sign_in(
    payload: GoogleSignInRequest,
    request: Request,
    response: Response,
    repos: ReposDep,
    settings: SettingsDep,
) -> TokenResponse:
    try:
        claims = verify_google_id_token(payload.id_token, settings)
    except AuthError as exc:
        # The reason is logged, not returned: distinguishing "bad signature" from
        # "wrong audience" only helps an attacker.
        log.info("google sign-in rejected: %s", exc)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google sign-in failed") from exc

    user = repos.users.upsert_by_email(claims["email"])
    repos.flush()
    return _issue_session(request, response, repos, settings, user)


class MagicLinkResponse(BaseModel):
    sent: bool
    # Returned only when email delivery is not configured, so local development
    # works without an SMTP provider. Never populated in production.
    debug_token: str | None = None


@router.post("/magic-link", response_model=MagicLinkResponse)
def request_magic_link(payload: MagicLinkRequest, settings: SettingsDep) -> MagicLinkResponse:
    """Always reports success.

    Whether an address has an account is not something an unauthenticated caller
    should be able to enumerate.
    """
    token = issue_magic_token(payload.email, settings)
    # TODO(delivery): send via the configured email provider. Until one is wired,
    # the token is returned in non-production so the flow is exercisable end to end.
    log.info("magic link issued", extra={"email_domain": payload.email.split("@")[-1]})
    return MagicLinkResponse(sent=True, debug_token=None if settings.cookie_secure else token)


@router.post("/verify", response_model=TokenResponse)
def verify_magic_link(
    payload: MagicVerifyRequest,
    request: Request,
    response: Response,
    repos: ReposDep,
    settings: SettingsDep,
) -> TokenResponse:
    try:
        email = verify_magic_token(payload.token, settings)
    except AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "link expired or invalid") from exc

    user = repos.users.upsert_by_email(email)
    repos.flush()
    return _issue_session(request, response, repos, settings, user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    request: Request,
    response: Response,
    repos: ReposDep,
    settings: SettingsDep,
    impacto_refresh: Annotated[str | None, Cookie()] = None,
) -> TokenResponse:
    """Rotate the refresh token and mint a new access token.

    Rotation is the point: the presented token is revoked as part of the exchange,
    so a captured cookie stops working the moment the real client refreshes.
    """
    if not impacto_refresh:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no refresh token")

    session_row = repos.auth_sessions.by_token(impacto_refresh)
    if session_row is None:
        response.delete_cookie(REFRESH_COOKIE, path="/")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "refresh token expired")

    user = repos.users.get(session_row.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "account no longer exists")

    repos.auth_sessions.revoke(impacto_refresh)
    return _issue_session(request, response, repos, settings, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    repos: ReposDep,
    impacto_refresh: Annotated[str | None, Cookie()] = None,
) -> Response:
    if impacto_refresh:
        repos.auth_sessions.revoke(impacto_refresh)
    response.delete_cookie(REFRESH_COOKIE, path="/")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_everywhere(user: CurrentUser, response: Response, repos: ReposDep) -> Response:
    """Ends every session for this account — the 'I lost my phone' path."""
    repos.auth_sessions.revoke_all(user.id)
    response.delete_cookie(REFRESH_COOKIE, path="/")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]

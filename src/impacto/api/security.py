"""Tokens and identity.

Three token kinds, deliberately different in lifetime and storage:

  access   15 min, JWT, sent as a Bearer header. Never stored server-side.
  refresh  30 days, opaque random string, stored *hashed* in `sessions` and sent
           only as an httpOnly Secure SameSite=Lax cookie.
  magic    single-use, short-lived JWT emailed to the user.

The access token is deliberately short-lived and unrevocable; revocation lives on
the refresh token, which is checked against the database on every rotation.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from ..config import Settings, get_settings

ALGORITHM = "HS256"
REFRESH_COOKIE = "impacto_refresh"

ACCESS_AUDIENCE = "impacto:access"
MAGIC_AUDIENCE = "impacto:magic"

GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}


class AuthError(Exception):
    """Any failure to establish identity. Always surfaces as 401, never as detail."""


@dataclass(frozen=True)
class TokenClaims:
    user_id: str
    email: str
    expires_at: datetime


def _secret(settings: Settings | None = None) -> str:
    s = settings or get_settings()
    if not s.jwt_secret:
        # Fail closed. A default signing secret is indistinguishable from no auth.
        raise AuthError("IMPACTO_JWT_SECRET is not configured")
    return s.jwt_secret


def _now() -> datetime:
    return datetime.now(UTC)


# ------------------------------------------------------------------- access
def issue_access_token(
    user_id: str, email: str, settings: Settings | None = None
) -> tuple[str, int]:
    """Return (jwt, seconds_until_expiry)."""
    s = settings or get_settings()
    expires = _now() + timedelta(minutes=s.access_token_minutes)
    token = jwt.encode(
        {
            "sub": str(user_id),
            "email": email,
            "aud": ACCESS_AUDIENCE,
            "iat": int(_now().timestamp()),
            "exp": int(expires.timestamp()),
        },
        _secret(s),
        algorithm=ALGORITHM,
    )
    return token, s.access_token_minutes * 60


def decode_access_token(token: str, settings: Settings | None = None) -> TokenClaims:
    s = settings or get_settings()
    try:
        payload = jwt.decode(
            token, _secret(s), algorithms=[ALGORITHM], audience=ACCESS_AUDIENCE
        )
    except jwt.PyJWTError as exc:
        raise AuthError(f"invalid access token: {exc}") from exc
    return TokenClaims(
        user_id=payload["sub"],
        email=payload.get("email", ""),
        expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
    )


# ------------------------------------------------------------------ refresh
def issue_refresh_token() -> str:
    """Opaque and high-entropy.

    Not a JWT: a refresh token must be revocable, and revocation means a database
    lookup either way — so there is nothing to gain from making it self-describing,
    and a signed token that outlives its revocation is a real hazard.
    """
    return secrets.token_urlsafe(48)


# -------------------------------------------------------------- magic link
def issue_magic_token(email: str, settings: Settings | None = None) -> str:
    s = settings or get_settings()
    return jwt.encode(
        {
            "email": UserEmail.normalise(email),
            "aud": MAGIC_AUDIENCE,
            "jti": secrets.token_urlsafe(16),
            "iat": int(_now().timestamp()),
            "exp": int((_now() + timedelta(minutes=s.magic_link_ttl_minutes)).timestamp()),
        },
        _secret(s),
        algorithm=ALGORITHM,
    )


def verify_magic_token(token: str, settings: Settings | None = None) -> str:
    """Return the verified email address."""
    s = settings or get_settings()
    try:
        payload = jwt.decode(
            token, _secret(s), algorithms=[ALGORITHM], audience=MAGIC_AUDIENCE
        )
    except jwt.PyJWTError as exc:
        raise AuthError(f"invalid or expired magic link: {exc}") from exc
    return payload["email"]


class UserEmail:
    @staticmethod
    def normalise(email: str) -> str:
        return email.strip().lower()


# ----------------------------------------------------------------- google
_jwks_client: jwt.PyJWKClient | None = None


def _jwks() -> jwt.PyJWKClient:
    # PyJWKClient caches the key set, so this is one network call per key rotation
    # rather than one per sign-in.
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(GOOGLE_JWKS_URL, cache_keys=True)
    return _jwks_client


def verify_google_id_token(
    id_token: str, settings: Settings | None = None, jwks_client=None
) -> dict:
    """Verify a Google ID token and return its claims.

    Signature, audience, issuer and expiry are all checked. `jwks_client` is
    injectable so tests can verify against a local key instead of the network.
    """
    s = settings or get_settings()
    if not s.google_client_id:
        raise AuthError("IMPACTO_GOOGLE_CLIENT_ID is not configured")
    try:
        key = (jwks_client or _jwks()).get_signing_key_from_jwt(id_token).key
        claims = jwt.decode(
            id_token,
            key,
            algorithms=["RS256"],
            audience=s.google_client_id,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthError(f"invalid Google ID token: {exc}") from exc

    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise AuthError("unexpected token issuer")
    if not claims.get("email"):
        raise AuthError("Google ID token carries no email")
    if claims.get("email_verified") is False:
        # An unverified address would let anyone claim someone else's account.
        raise AuthError("Google email address is not verified")
    return claims


__all__ = [
    "AuthError",
    "TokenClaims",
    "REFRESH_COOKIE",
    "issue_access_token",
    "decode_access_token",
    "issue_refresh_token",
    "issue_magic_token",
    "verify_magic_token",
    "verify_google_id_token",
]

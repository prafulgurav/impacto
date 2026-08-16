"""Portable column types.

Production runs Postgres 16. The test suite must stay hermetic and fast, so it runs
the same models against SQLite. Every type here therefore resolves to the native
Postgres type where one exists and to a SQLite-compatible equivalent otherwise —
which means the schema under test is the schema that ships, rather than a
hand-maintained parallel definition that quietly drifts.
"""
from __future__ import annotations

import base64
import os
from decimal import Decimal

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import JSON, DateTime, LargeBinary, Numeric, TypeDecorator, Uuid
from sqlalchemy.dialects.postgresql import JSONB

# JSONB on Postgres (indexable, binary), plain JSON on SQLite.
JsonB = JSON().with_variant(JSONB(), "postgresql")

# Native uuid on Postgres, CHAR(32) on SQLite — SQLAlchemy 2.0 handles both.
UUIDType = Uuid(as_uuid=True)

# Every timestamp in this schema is absolute. SEBI's five-year retention obligation
# is meaningless if the record's timezone is ambiguous.
TimestampTZ = DateTime(timezone=True)

_KEY_ENV = "IMPACTO_HOLDINGS_ENCRYPTION_KEY"
_NONCE_BYTES = 12


class MissingEncryptionKey(RuntimeError):
    """Raised when holdings are touched without a configured key.

    Deliberately fatal rather than falling back to plaintext: portfolio holdings are
    financial PII, and a deployment that silently stored them unencrypted would be a
    worse outcome than one that refuses to store them at all.
    """


def _configured_key() -> str | None:
    """Prefer the raw env var so a test can set it without clearing the settings cache."""
    if raw := os.environ.get(_KEY_ENV):
        return raw
    from ..config import get_settings

    return get_settings().holdings_encryption_key


def _aesgcm() -> AESGCM:
    raw = _configured_key()
    if not raw:
        raise MissingEncryptionKey(
            f"{_KEY_ENV} is not set; holdings cannot be read or written. "
            "Generate one with: python -c \"import base64,os;"
            'print(base64.b64encode(os.urandom(32)).decode())"'
        )
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception as exc:
        raise MissingEncryptionKey(f"{_KEY_ENV} must be base64") from exc
    if len(key) not in (16, 24, 32):
        raise MissingEncryptionKey(f"{_KEY_ENV} must decode to 16, 24 or 32 bytes")
    return AESGCM(key)


def generate_encryption_key() -> str:
    """A fresh base64 key, for `.env` bootstrapping and for tests."""
    return base64.b64encode(os.urandom(32)).decode()


class _EncryptedBlob(TypeDecorator):
    """Application-level AES-GCM, stored as opaque bytes.

    A random nonce is prepended to each ciphertext, so the same plaintext encrypts
    differently every time — an attacker with table access cannot tell which users
    hold the same symbol. That also means these columns are not searchable, which is
    the intended trade: the server never needs to query by holding.
    """

    impl = LargeBinary
    cache_ok = True

    def _to_text(self, value) -> str:
        raise NotImplementedError

    def _from_text(self, text: str):
        raise NotImplementedError

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        nonce = os.urandom(_NONCE_BYTES)
        return nonce + _aesgcm().encrypt(nonce, self._to_text(value).encode(), None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        blob = bytes(value)
        try:
            plain = _aesgcm().decrypt(blob[:_NONCE_BYTES], blob[_NONCE_BYTES:], None)
        except InvalidTag as exc:
            # Wrong key, or the row was tampered with. Both are fatal, not skippable.
            raise MissingEncryptionKey(
                "holdings could not be decrypted; the encryption key has changed"
            ) from exc
        return self._from_text(plain.decode())


class EncryptedString(_EncryptedBlob):
    """An encrypted text column that behaves like `str` in Python."""

    def _to_text(self, value) -> str:
        return str(value)

    def _from_text(self, text: str) -> str:
        return text


class EncryptedNumeric(_EncryptedBlob):
    """An encrypted numeric column that behaves like `Decimal` in Python.

    Serialised as a decimal string rather than a float so a portfolio weight
    round-trips exactly.
    """

    def _to_text(self, value) -> str:
        return str(Decimal(str(value)))

    def _from_text(self, text: str) -> Decimal:
        return Decimal(text)


__all__ = [
    "JsonB",
    "UUIDType",
    "TimestampTZ",
    "Numeric",
    "EncryptedString",
    "EncryptedNumeric",
    "MissingEncryptionKey",
    "generate_encryption_key",
]

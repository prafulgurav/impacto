"""Runtime configuration. Everything is env-overridable; nothing secret is committed."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]

ENV_PREFIX = "IMPACTO_"
LEGACY_ENV_PREFIX = "GP_"

# Per-provider defaults. `llm_model` overrides whichever provider is active, which
# keeps a single-provider deployment to one env var while still allowing both to be
# configured side by side for a failover or an A/B.
DEFAULT_MODELS = {
    "anthropic": "claude-opus-5",
    "gemini": "gemini-2.5-flash",
}


def _adopt_legacy_env() -> None:
    """Map any `GP_*` var onto its `IMPACTO_*` equivalent.

    The engine shipped with the `GP_` prefix before the rebrand. Existing
    deployments and `.env` files keep working; an explicit `IMPACTO_*` always wins.
    """
    for key, value in list(os.environ.items()):
        if not key.startswith(LEGACY_ENV_PREFIX):
            continue
        new_key = ENV_PREFIX + key[len(LEGACY_ENV_PREFIX):]
        os.environ.setdefault(new_key, value)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX, env_file=".env", extra="ignore"
    )

    # --- paths -------------------------------------------------------------
    knowledge_dir: Path = Field(default=REPO_ROOT / "knowledge")
    fixtures_dir: Path = Field(default=REPO_ROOT / "data" / "fixtures")
    cache_dir: Path = Field(default=REPO_ROOT / "data" / "cache")

    # --- data providers ----------------------------------------------------
    # "fixture" = deterministic bundled data (offline, used by tests and demo)
    # "yfinance" = live free provider
    market_provider: str = Field(default="fixture")
    fred_api_key: str | None = Field(default=None)
    gdelt_enabled: bool = Field(default=True)
    news_rss_feeds: str = Field(
        default=(
            "https://www.moneycontrol.com/rss/marketreports.xml,"
            "https://www.moneycontrol.com/rss/economy.xml,"
            "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms,"
            "https://www.livemint.com/rss/markets"
        )
    )

    # --- event study defaults ---------------------------------------------
    estimation_window: int = Field(default=120)
    estimation_gap: int = Field(default=10)   # sessions between estimation window end and event
    min_estimation_obs: int = Field(default=60)

    # --- LLM ---------------------------------------------------------------
    # none | anthropic | gemini | auto. "none" is fully deterministic and is how CI
    # runs; "auto" picks whichever provider has a key configured.
    llm_provider: str = Field(default="none")
    llm_model: str | None = Field(default=None)   # overrides the active provider's default
    llm_max_tokens: int = Field(default=1200)
    llm_timeout_seconds: float = Field(default=30.0)
    anthropic_api_key: str | None = Field(default=None)
    anthropic_model: str | None = Field(default=None)
    gemini_api_key: str | None = Field(default=None)
    gemini_model: str | None = Field(default=None)

    # --- persistence -------------------------------------------------------
    # Postgres in production; SQLite by default so a clone runs with no services.
    database_url: str = Field(default=f"sqlite:///{REPO_ROOT / 'data' / 'impacto.db'}")
    redis_url: str | None = Field(default=None)
    # Base64 AES key for holdings-at-rest. Absent means holdings cannot be stored.
    holdings_encryption_key: str | None = Field(default=None)

    # --- scheduled jobs ----------------------------------------------------
    # All times are IST; the scheduler is pinned to Asia/Kolkata.
    scheduler_enabled: bool = Field(default=False)
    scheduler_timezone: str = Field(default="Asia/Kolkata")
    precompute_hour: int = Field(default=2)          # 02:00 IST daily
    precompute_minute: int = Field(default=0)
    precompute_keep_days: int = Field(default=7)     # retain a week of as_of slices
    ingest_interval_minutes: int = Field(default=30)  # every 30 min, 06:00-23:00 IST
    ingest_start_hour: int = Field(default=6)
    ingest_end_hour: int = Field(default=23)
    digest_hour: int = Field(default=7)              # 07:30 IST weekdays
    digest_minute: int = Field(default=30)
    digest_lookback_days: int = Field(default=3)

    # The five windows precomputed nightly (§2.2). The first is what the offline
    # bundle ships, so it is also the default for every read endpoint.
    analog_windows: str = Field(
        default="T+1..T+5,T+0,T+0..T+3,T+0..T+10,T+1..T+21"
    )

    # --- auth --------------------------------------------------------------
    # No passwords: Google OAuth and email magic link only (§2.3). Indian mobile
    # users abandon password forms, and a password store is a liability we would
    # gain nothing from.
    jwt_secret: str | None = Field(default=None)
    access_token_minutes: int = Field(default=15)
    refresh_token_days: int = Field(default=30)
    google_client_id: str | None = Field(default=None)
    magic_link_ttl_minutes: int = Field(default=15)
    cookie_secure: bool = Field(default=True)   # False only for plain-HTTP local dev
    cookie_domain: str | None = Field(default=None)

    # --- web push ----------------------------------------------------------
    vapid_public_key: str | None = Field(default=None)
    vapid_private_key: str | None = Field(default=None)
    vapid_subject: str = Field(default="mailto:alerts@impacto.app")

    # --- api hardening -----------------------------------------------------
    web_origin: str = Field(default="http://localhost:3000")
    rate_limit_anonymous: int = Field(default=60)        # per minute
    rate_limit_authenticated: int = Field(default=300)
    rate_limit_explain: int = Field(default=10)          # LLM tokens cost money
    # Response-cache TTLs, seconds. Mirrors the service-worker strategy table so the
    # SW and the server agree on how stale a payload may be.
    cache_ttl_knowledge: int = Field(default=7 * 24 * 3600)
    cache_ttl_analogs: int = Field(default=24 * 3600)
    cache_ttl_digest: int = Field(default=3600)
    cache_ttl_bundle: int = Field(default=3600)
    bundle_max_bytes: int = Field(default=300 * 1024)     # gzipped target (§3)
    bundle_event_days: int = Field(default=30)

    # --- compliance --------------------------------------------------------
    # Hard switch. When True the guardrail layer rejects any output containing
    # directional/forward-looking language about a named security. See COMPLIANCE.md.
    compliance_mode: bool = Field(default=True)
    jurisdiction: str = Field(default="IN")

    @property
    def rss_feed_list(self) -> list[str]:
        return [f.strip() for f in self.news_rss_feeds.split(",") if f.strip()]

    @property
    def analog_window_list(self) -> list[str]:
        return [w.strip() for w in self.analog_windows.split(",") if w.strip()]

    @property
    def default_window(self) -> str:
        """The window the offline bundle and every un-parameterised read endpoint use."""
        windows = self.analog_window_list
        return windows[0] if windows else "T+1..T+5"

    def resolved_llm_model(self, provider: str) -> str:
        """Model id for `provider`, most specific setting first."""
        per_provider = {
            "anthropic": self.anthropic_model,
            "gemini": self.gemini_model,
        }.get(provider)
        return per_provider or self.llm_model or DEFAULT_MODELS.get(provider, "")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _adopt_legacy_env()
    return Settings()


def reset_settings_cache() -> None:
    """Used by tests after mutating os.environ."""
    get_settings.cache_clear()


__all__ = [
    "Settings",
    "get_settings",
    "reset_settings_cache",
    "REPO_ROOT",
    "DEFAULT_MODELS",
]

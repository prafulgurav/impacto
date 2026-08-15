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

    # --- compliance --------------------------------------------------------
    # Hard switch. When True the guardrail layer rejects any output containing
    # directional/forward-looking language about a named security. See COMPLIANCE.md.
    compliance_mode: bool = Field(default=True)
    jurisdiction: str = Field(default="IN")

    @property
    def rss_feed_list(self) -> list[str]:
        return [f.strip() for f in self.news_rss_feeds.split(",") if f.strip()]

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

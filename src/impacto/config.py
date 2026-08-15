"""Runtime configuration. Everything is env-overridable; nothing secret is committed."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GP_", env_file=".env", extra="ignore")

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
    llm_provider: str = Field(default="none")     # none | anthropic | openai
    llm_model: str = Field(default="claude-opus-4-5")
    anthropic_api_key: str | None = Field(default=None)

    # --- compliance --------------------------------------------------------
    # Hard switch. When True the guardrail layer rejects any output containing
    # directional/forward-looking language about a named security. See COMPLIANCE.md.
    compliance_mode: bool = Field(default=True)
    jurisdiction: str = Field(default="IN")

    @property
    def rss_feed_list(self) -> list[str]:
        return [f.strip() for f in self.news_rss_feeds.split(",") if f.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Used by tests after mutating os.environ."""
    get_settings.cache_clear()


__all__ = ["Settings", "get_settings", "reset_settings_cache", "REPO_ROOT"]

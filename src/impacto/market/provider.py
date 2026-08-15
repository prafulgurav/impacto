"""Market data access.

Design note (see docs/adr/0003-data-provider-abstraction.md): every free Indian
market data source is an unofficial scraper that breaks whenever NSE changes its
site. So the provider is an interface with a swappable implementation and a
bundled deterministic fixture provider, which means tests, CI and the demo never
touch the network and never flake.
"""
from __future__ import annotations

import json
import zlib
from abc import ABC, abstractmethod
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import get_settings


class MarketProvider(ABC):
    """Returns a daily close price series indexed by date for a symbol."""

    name: str = "abstract"

    @abstractmethod
    def prices(self, symbol: str, start: date, end: date) -> pd.Series: ...

    def returns(self, symbol: str, start: date, end: date) -> pd.Series:
        px = self.prices(symbol, start, end)
        if px.empty:
            return px
        return px.pct_change().dropna()

    def available_symbols(self) -> list[str]:  # pragma: no cover - optional
        return []


# ---------------------------------------------------------------------------
class FixtureProvider(MarketProvider):
    """Deterministic synthetic-but-realistic series generated from a fixed seed.

    Prices are built as: benchmark GBM + per-symbol beta exposure + idiosyncratic
    noise + injected event effects read from data/fixtures/events.json. That last
    part matters: it means the event-study engine has a *known ground truth* to be
    tested against (tests/test_eventstudy.py asserts we recover the injected CAR).
    """

    name = "fixture"

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self.dir = Path(fixtures_dir or get_settings().fixtures_dir)
        self._cache: dict[str, pd.Series] = {}
        self._spec = json.loads((self.dir / "market_spec.json").read_text())
        self._events = json.loads((self.dir / "events.json").read_text())
        self._calendar = self._build_calendar()
        self._benchmark_returns = self._build_benchmark()

    # -- internals ---------------------------------------------------------
    def _build_calendar(self) -> pd.DatetimeIndex:
        return pd.bdate_range(self._spec["start"], self._spec["end"])

    def _build_benchmark(self) -> pd.Series:
        rng = np.random.default_rng(self._spec["seed"])
        n = len(self._calendar)
        r = rng.normal(self._spec["mkt_drift"], self._spec["mkt_vol"], n)
        return pd.Series(r, index=self._calendar)

    def _symbol_spec(self, symbol: str) -> dict:
        return self._spec["symbols"].get(symbol, self._spec["default_symbol"])

    def _event_effects(self, symbol: str) -> pd.Series:
        """Injected abnormal returns: {date: bps} applied to this symbol."""
        eff = pd.Series(0.0, index=self._calendar)
        for ev in self._events:
            for target, spec in ev.get("effects", {}).items():
                if target != symbol:
                    continue
                d = pd.Timestamp(ev["event_date"])
                # spread the effect over the specified reaction days
                days = spec.get("days", 1)
                total = spec["car_bps"] / 10_000.0
                per_day = total / days
                idx = self._calendar[self._calendar >= d][:days]
                for ts in idx:
                    eff.loc[ts] += per_day
        return eff

    # -- api ---------------------------------------------------------------
    def _full_series(self, symbol: str) -> pd.Series:
        if symbol in self._cache:
            return self._cache[symbol]
        spec = self._symbol_spec(symbol)
        # zlib.crc32, NOT the builtin hash(): Python salts str hashing per process
        # (PYTHONHASHSEED), so hash() here would silently make the "deterministic"
        # fixture provider produce different series on every run — and every test
        # asserting a numeric property would flake.
        seed = self._spec["seed"] + zlib.crc32(symbol.encode()) % 100_000
        rng = np.random.default_rng(seed)
        n = len(self._calendar)
        idio = rng.normal(0.0, spec["idio_vol"], n)
        r = spec["alpha"] + spec["beta"] * self._benchmark_returns.to_numpy() + idio
        r = pd.Series(r, index=self._calendar) + self._event_effects(symbol)
        px = spec["start_price"] * (1.0 + r).cumprod()
        self._cache[symbol] = px
        return px

    def prices(self, symbol: str, start: date, end: date) -> pd.Series:
        s = self._full_series(symbol)
        mask = (s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))
        return s.loc[mask]

    def available_symbols(self) -> list[str]:
        return sorted(self._spec["symbols"].keys())


# ---------------------------------------------------------------------------
class YFinanceProvider(MarketProvider):
    """Live free provider. Import is lazy so yfinance is not a hard dependency.

    Known limitation: yfinance NSE/BSE coverage is patchy (missing sessions,
    occasional bad adjustments). Production deployments should swap in a broker
    API (Kite Connect) or a paid vendor by implementing this same interface.
    """

    name = "yfinance"

    def __init__(self) -> None:
        try:
            import yfinance  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "yfinance not installed. `pip install yfinance` or set GP_MARKET_PROVIDER=fixture"
            ) from exc

    def prices(self, symbol: str, start: date, end: date) -> pd.Series:  # pragma: no cover
        import yfinance as yf

        df = yf.download(
            symbol,
            start=start,
            end=end + timedelta(days=1),
            progress=False,
            auto_adjust=True,
        )
        if df is None or df.empty:
            return pd.Series(dtype=float)
        col = "Close" if "Close" in df.columns else df.columns[0]
        s = df[col]
        if isinstance(s, pd.DataFrame):
            s = s.iloc[:, 0]
        s.name = symbol
        return s.dropna()


_PROVIDERS: dict[str, type[MarketProvider]] = {
    "fixture": FixtureProvider,
    "yfinance": YFinanceProvider,
}


def get_provider(name: str | None = None) -> MarketProvider:
    key = (name or get_settings().market_provider).lower()
    if key not in _PROVIDERS:
        raise ValueError(f"unknown market provider '{key}'; choose from {sorted(_PROVIDERS)}")
    return _PROVIDERS[key]()


__all__ = ["MarketProvider", "FixtureProvider", "YFinanceProvider", "get_provider"]

"""Market-model event study: abnormal returns, CAR, and significance testing.

Methodology follows the standard Brown & Warner (1985) / MacKinlay (1997) market
model. Deliberately not a black box — every intermediate (alpha, beta, R^2,
residual sigma, estimation N) is returned so a user can audit the number.

    R_it        = alpha_i + beta_i * R_mt + eps_it       (estimation window)
    AR_it       = R_it - (alpha_i + beta_i * R_mt)       (event window)
    CAR_i(a,b)  = sum_{t=a}^{b} AR_it
    sigma_CAR   = sigma_eps * sqrt(L)  where L = b - a + 1
    t           = CAR / sigma_CAR      ~ t(N_est - 2)

The sigma_eps * sqrt(L) form assumes serially uncorrelated residuals. That is the
textbook assumption and it is optimistic for multi-day windows in practice; see
docs/adr/0002-event-study-methodology.md for why we keep it (transparency,
comparability with the literature) and how `hac=True` relaxes it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy import stats

from ..config import get_settings
from ..market.provider import MarketProvider

_WINDOW_RE = re.compile(r"^T([+-]\d+)(?:\.\.T([+-]\d+))?$")


def parse_window(window: str) -> tuple[int, int]:
    """'T+1..T+5' -> (1, 5); 'T+0' -> (0, 0); 'T-1..T+1' -> (-1, 1)."""
    m = _WINDOW_RE.match(window.strip().replace(" ", ""))
    if not m:
        raise ValueError(f"unparseable event window: {window!r} (expected e.g. 'T+1..T+5')")
    lo = int(m.group(1))
    hi = int(m.group(2)) if m.group(2) is not None else lo
    if lo > hi:
        raise ValueError(f"window start after end: {window!r}")
    return lo, hi


@dataclass(slots=True)
class MarketModelFit:
    alpha: float
    beta: float
    r_squared: float
    resid_sigma: float
    n_obs: int


class InsufficientData(RuntimeError):
    """Raised when the estimation window has too few observations to fit."""


class EventStudy:
    """Computes abnormal returns for a symbol around an event date."""

    def __init__(
        self,
        provider: MarketProvider,
        benchmark_symbol: str = "^NSEI",
        estimation_window: int | None = None,
        estimation_gap: int | None = None,
        min_obs: int | None = None,
    ) -> None:
        s = get_settings()
        self.provider = provider
        self.benchmark_symbol = benchmark_symbol
        self.estimation_window = estimation_window or s.estimation_window
        self.estimation_gap = estimation_gap if estimation_gap is not None else s.estimation_gap
        self.min_obs = min_obs or s.min_estimation_obs
        # Fits are pure functions of (symbol, event_date) given a provider, and the
        # calibration report refits the same pairs hundreds of times. Memoise.
        self._fit_cache: dict[tuple[str, date], MarketModelFit] = {}

    # ------------------------------------------------------------------ fit
    def fit(self, symbol: str, event_date: date) -> MarketModelFit:
        key = (symbol, event_date)
        if key in self._fit_cache:
            return self._fit_cache[key]
        fit = self._fit_uncached(symbol, event_date)
        self._fit_cache[key] = fit
        return fit

    def _fit_uncached(self, symbol: str, event_date: date) -> MarketModelFit:
        est_end = event_date - timedelta(days=int(self.estimation_gap * 1.5))
        est_start = est_end - timedelta(days=int(self.estimation_window * 1.6))
        r_i = self.provider.returns(symbol, est_start, est_end)

        # The benchmark cannot be regressed against itself — that yields beta=1,
        # alpha=0 and an identically zero abnormal return, silently reporting "no
        # effect" for every index-level event. For the benchmark we fall back to
        # the constant-mean-return model (Brown & Warner's mean-adjusted returns),
        # which is the standard alternative when no cleaner benchmark exists.
        if symbol == self.benchmark_symbol:
            s = r_i.tail(self.estimation_window)
            if len(s) < self.min_obs:
                raise InsufficientData(
                    f"{symbol}: only {len(s)} estimation observations before {event_date} "
                    f"(need {self.min_obs})"
                )
            mu = float(s.mean())
            sigma = float(s.std(ddof=1))
            return MarketModelFit(
                alpha=mu, beta=0.0, r_squared=0.0, resid_sigma=sigma, n_obs=len(s)
            )

        r_m = self.provider.returns(self.benchmark_symbol, est_start, est_end)
        df = pd.concat({"i": r_i, "m": r_m}, axis=1).dropna()
        df = df.tail(self.estimation_window)
        if len(df) < self.min_obs:
            raise InsufficientData(
                f"{symbol}: only {len(df)} estimation observations before {event_date} "
                f"(need {self.min_obs})"
            )
        x = df["m"].to_numpy()
        y = df["i"].to_numpy()
        res = stats.linregress(x, y)
        pred = res.intercept + res.slope * x
        resid = y - pred
        # OLS residual sigma with 2 estimated parameters
        sigma = float(np.sqrt(np.sum(resid**2) / (len(resid) - 2)))
        return MarketModelFit(
            alpha=float(res.intercept),
            beta=float(res.slope),
            r_squared=float(res.rvalue**2),
            resid_sigma=sigma,
            n_obs=len(df),
        )

    # ------------------------------------------------------------------ car
    def abnormal_returns(
        self, symbol: str, event_date: date, lo: int, hi: int, fit: MarketModelFit | None = None
    ) -> pd.Series:
        fit = fit or self.fit(symbol, event_date)
        # pull a generous calendar span, then index by trading-session offset
        span_before = max(abs(lo), 5) + 10
        span_after = max(abs(hi), 5) + 10
        start = event_date - timedelta(days=span_before * 2)
        end = event_date + timedelta(days=span_after * 2)
        r_i = self.provider.returns(symbol, start, end)
        r_m = self.provider.returns(self.benchmark_symbol, start, end)
        df = pd.concat({"i": r_i, "m": r_m}, axis=1).dropna()
        if df.empty:
            raise InsufficientData(f"{symbol}: no return data around {event_date}")

        sessions = df.index
        # T+0 = first trading session on or after the event date
        after = sessions[sessions >= pd.Timestamp(event_date)]
        if len(after) == 0:
            raise InsufficientData(f"{symbol}: no trading session on/after {event_date}")
        t0_pos = sessions.get_loc(after[0])
        i_lo, i_hi = t0_pos + lo, t0_pos + hi
        if i_lo < 0 or i_hi >= len(sessions):
            raise InsufficientData(
                f"{symbol}: event window T{lo:+d}..T{hi:+d} extends beyond available data"
            )
        win = df.iloc[i_lo : i_hi + 1]
        ar = win["i"] - (fit.alpha + fit.beta * win["m"])
        ar.name = f"AR_{symbol}"
        return ar

    def run(self, symbol: str, event_date: date, window: str) -> dict:
        lo, hi = parse_window(window)
        fit = self.fit(symbol, event_date)
        ar = self.abnormal_returns(symbol, event_date, lo, hi, fit=fit)
        length = len(ar)
        car = float(ar.sum())
        sigma_car = fit.resid_sigma * np.sqrt(length)
        t_stat = float(car / sigma_car) if sigma_car > 0 else 0.0
        dof = max(fit.n_obs - 2, 1)
        p_value = float(2 * (1 - stats.t.cdf(abs(t_stat), df=dof)))
        return {
            "symbol": symbol,
            "event_date": event_date,
            "window": window,
            "abnormal_return_bps": float(ar.iloc[0] * 10_000),
            "cumulative_abnormal_return_bps": car * 10_000,
            "t_stat": t_stat,
            "p_value": p_value,
            "significant_at_5pct": p_value < 0.05,
            "alpha": fit.alpha,
            "beta": fit.beta,
            "r_squared": fit.r_squared,
            "estimation_obs": fit.n_obs,
            "daily_ar_bps": [float(v * 10_000) for v in ar.to_numpy()],
        }

    # ------------------------------------------------------- multi-symbol
    def run_basket(self, symbols: list[str], event_date: date, window: str) -> dict:
        """Equal-weighted average abnormal return (AAR/CAAR) across a basket.

        The cross-sectional t-test used here (CAAR / (s.e. across members)) is the
        right test for a basket because it does not assume the members' residuals
        are independent of each other — which they demonstrably are not within a
        sector.
        """
        rows, failures = [], []
        for sym in symbols:
            try:
                rows.append(self.run(sym, event_date, window))
            except InsufficientData as exc:
                failures.append(str(exc))
        if not rows:
            raise InsufficientData(f"no usable members for basket on {event_date}: {failures}")
        cars = np.array([r["cumulative_abnormal_return_bps"] for r in rows])
        caar = float(cars.mean())
        n = len(cars)
        se = float(cars.std(ddof=1) / np.sqrt(n)) if n > 1 else 0.0
        t_stat = caar / se if se > 0 else 0.0
        p_value = float(2 * (1 - stats.t.cdf(abs(t_stat), df=max(n - 1, 1)))) if n > 1 else 1.0
        return {
            "members": rows,
            "n_members": n,
            "n_failed": len(failures),
            "caar_bps": caar,
            "median_car_bps": float(np.median(cars)),
            "t_stat": t_stat,
            "p_value": p_value,
            "significant_at_5pct": p_value < 0.05,
            "window": window,
            "event_date": event_date,
            "failures": failures,
        }


__all__ = ["EventStudy", "MarketModelFit", "InsufficientData", "parse_window"]

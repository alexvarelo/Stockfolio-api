"""Pure portfolio-risk calculations (pandas/numpy only, no network)."""
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

TRADING_DAYS = 252
MIN_OBSERVATIONS = 30
FFILL_LIMIT = 3


def normalize_index(s: pd.Series) -> pd.Series:
    """Tz-naive, day-normalised, sorted, de-duplicated series."""
    s = s.dropna()
    idx = pd.DatetimeIndex(s.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    s = pd.Series(s.to_numpy(dtype=float), index=idx.normalize())
    s = s[~s.index.duplicated(keep="last")]
    return s.sort_index()


def to_base_currency(price: pd.Series, fx: Optional[pd.Series] = None,
                     pence: bool = False, ffill_limit: int = FFILL_LIMIT) -> pd.Series:
    """Convert a local-currency price series to base currency.

    fx is the base-per-local rate (e.g. EURUSD=X for EUR assets in USD).
    pence=True divides by 100 first (GBp -> GBP).
    """
    out = price / 100.0 if pence else price
    if fx is not None:
        union = out.index.union(fx.index)
        rate = fx.reindex(union).ffill(limit=ffill_limit).reindex(out.index)
        out = out * rate
    return out.dropna()


def align_prices(series: Dict[str, pd.Series], ffill_limit: int = FFILL_LIMIT) -> pd.DataFrame:
    """Inner-join series on common dates, forward-filling gaps of at most `ffill_limit` days."""
    if not series:
        return pd.DataFrame()
    df = pd.concat(series, axis=1).sort_index()
    df = df.ffill(limit=ffill_limit)
    return df.dropna(how="any")


def portfolio_value(prices: pd.DataFrame, quantities: Dict[str, float]) -> pd.Series:
    """Buy-and-hold value series: sum(qty_i * price_i(t))."""
    q = pd.Series(quantities, dtype=float).reindex(prices.columns)
    return (prices * q).sum(axis=1)


def max_drawdown(values: pd.Series) -> Optional[float]:
    """Most negative peak-to-trough fraction (<= 0)."""
    if len(values) < 2:
        return None
    dd = values / values.cummax() - 1.0
    return float(dd.min())


def compute_risk(prices: pd.DataFrame, quantities: Dict[str, float],
                 benchmark: Optional[pd.Series] = None, risk_free_rate: float = 0.0,
                 min_observations: int = MIN_OBSERVATIONS) -> dict:
    """Compute risk metrics.

    prices: aligned base-currency close prices, one column per ticker.
    benchmark: benchmark close series (any index; aligned here by inner join).
    """
    tickers = list(prices.columns)
    if benchmark is not None:
        joined = pd.concat([prices, benchmark.rename("__bench__")], axis=1).dropna()
        bench = joined["__bench__"]
        prices = joined[tickers]
    else:
        bench = None

    values = portfolio_value(prices, quantities)
    last = prices.iloc[-1]
    qty = pd.Series(quantities, dtype=float).reindex(tickers)
    pos_value = qty * last
    total = float(pos_value.sum())
    weights = (pos_value / total).astype(float)

    hhi = float((weights ** 2).sum())
    top = weights.idxmax()

    rets = prices.pct_change().dropna()
    port_ret = values.pct_change().dropna()
    n = len(port_ret)
    enough = n >= min_observations

    beta = vol = sharpe = ann_ret = None
    if enough:
        vol = float(port_ret.std(ddof=1) * np.sqrt(TRADING_DAYS))
        if bench is not None:
            b = bench.pct_change().dropna()
            var_b = b.var(ddof=1)
            if var_b > 0:
                beta = float(np.cov(port_ret, b, ddof=1)[0, 1] / var_b)
        if vol > 0:
            excess = port_ret - risk_free_rate / TRADING_DAYS
            sharpe = float(excess.mean() * TRADING_DAYS / vol)
    if enough and values.iloc[0] > 0:
        ann_ret = float((values.iloc[-1] / values.iloc[0]) ** (TRADING_DAYS / n) - 1.0)

    if len(tickers) == 1:
        matrix: List[List[Optional[float]]] = [[1.0]]
    else:
        corr = rets.corr() if len(rets) >= 2 else pd.DataFrame(np.nan, index=tickers, columns=tickers)
        matrix = [[None if pd.isna(v) else float(v) for v in row] for row in corr.to_numpy()]

    return {
        "as_of": prices.index[-1].date(),
        "total_value": total,
        "position_values": {t: float(pos_value[t]) for t in tickers},
        "weights": {t: float(weights[t]) for t in tickers},
        "beta": beta,
        "volatility_annual": vol,
        "annual_return": ann_ret,
        "max_drawdown": max_drawdown(values),
        "sharpe_ratio": sharpe,
        "largest_position": {"ticker": str(top), "weight": float(weights[top])},
        "hhi": hhi,
        "effective_positions": float(1.0 / hhi) if hhi > 0 else None,
        "correlation": {"tickers": tickers, "matrix": matrix},
        "observations": int(n),
    }

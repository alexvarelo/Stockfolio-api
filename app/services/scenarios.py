"""Pure scenario maths (numpy/pandas only, no network): stress windows and Monte Carlo bootstrap."""
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

TRADING_DAYS = 252
CONTRIBUTION_STEP = 21
DEFAULT_SEED = 42
MAX_POINTS = 260
PCTS = (5, 25, 50, 75, 95)
MIN_BETA_WEEKS = 52
MAX_BUDGET = 100_000_000  # paths x days x assets

HISTORICAL_WINDOWS = [
    ("gfc_2008", "Global financial crisis (S&P 500 peak to trough)", "2007-10-09", "2009-03-09"),
    ("covid_2020", "COVID-19 crash", "2020-02-19", "2020-03-23"),
    ("bear_2022", "2022 bear market", "2022-01-03", "2022-10-12"),
]


# ---------------- stress ----------------
def window_return(series: pd.Series, start: str, end: str, min_coverage: float = 0.9) -> Optional[float]:
    """Total return of `series` over [start, end], or None if its data covers < min_coverage
    of the window's calendar span."""
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    w = series.loc[s:e]
    if len(w) < 2:
        return None
    span = (e - s).days
    if (w.index[-1] - w.index[0]).days / span < min_coverage:
        return None
    if w.iloc[0] <= 0:
        return None
    return float(w.iloc[-1] / w.iloc[0] - 1.0)


def clamp_beta(beta: Optional[float]) -> float:
    if beta is None or not np.isfinite(beta):
        return 1.0
    return float(min(3.0, max(0.0, beta)))


def proxy_return(beta: float, bench_ret: float) -> float:
    """Beta proxy on compounded returns: (1 + bench)^beta - 1 (floored at -100%)."""
    return max(-1.0, float((1.0 + bench_ret) ** beta - 1.0))


def weekly_beta(series: pd.Series, bench: pd.Series, years: int = 2, min_obs: int = MIN_BETA_WEEKS) -> float:
    """Beta from weekly (W-FRI) returns of `series` vs `bench` (both base currency) over the last
    `years` years. Weekly sampling avoids close-time asynchrony between markets. Returns the raw
    value clamped to [0, 3], or 1.0 when there are < min_obs weekly observations."""
    cutoff = bench.index[-1] - pd.Timedelta(days=365 * years)
    w = pd.concat([series.loc[cutoff:].resample("W-FRI").last(),
                   bench.loc[cutoff:].resample("W-FRI").last()], axis=1, keys=["s", "b"]).dropna()
    r = w.pct_change().dropna()
    r = r[np.isfinite(r).all(axis=1)]
    if len(r) < min_obs:
        return 1.0
    var_b = r["b"].var(ddof=1)
    if not var_b > 0:
        return 1.0
    return clamp_beta(float(np.cov(r["s"], r["b"], ddof=1)[0, 1] / var_b))


# ---------------- Monte Carlo ----------------
def bootstrap_indices(n_obs: int, paths: int, days: int, seed: int) -> np.ndarray:
    """Day indices (paths x days). Whole days are sampled, so cross-asset correlation is kept."""
    rng = np.random.default_rng(seed)
    return rng.integers(0, n_obs, size=(paths, days), dtype=np.int32)


def sample_returns(returns: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """(paths, days, assets) sampled daily return vectors."""
    return returns[idx]


def sample_days(days: int, max_points: int = MAX_POINTS) -> np.ndarray:
    """Sorted day numbers (0..days) at which percentiles are reported (<= max_points)."""
    return np.unique(np.linspace(0, days, min(days + 1, max_points)).round().astype(int))


def simulate(returns: np.ndarray, start_values: np.ndarray, idx: np.ndarray,
             monthly_contribution: float = 0.0, step: int = CONTRIBUTION_STEP,
             dtype=np.float32, chunk: int = 1000, no_contrib: Optional[np.ndarray] = None) -> dict:
    """Buy-and-hold Monte Carlo on bootstrapped joint daily returns.

    returns: (T, N) simple daily returns; start_values: (N,) money per asset at day 0
    (zeros allowed); idx: (paths, days) bootstrap indices.
    A contribution is added after every full `step`-day block (days // step times), split
    pro-rata to the weights at that moment. Asset values compound via cumulative sums of
    log-returns. Drawdown is time-weighted (the running peak is scaled up by contributions).

    no_contrib: optional boolean mask (N,) of columns (e.g. cash) that do not receive contributions;
    those go pro-rata to the remaining columns.

    Returns {"days": sampled day numbers, "values": (paths, len(days)) portfolio values
    (post-contribution), "min_drawdown": (paths,)}.
    """
    P, D = idx.shape
    logr = np.log1p(np.asarray(returns, dtype=np.float64)).astype(dtype)
    v0 = np.asarray(start_values, dtype=dtype)
    sel = sample_days(D)
    values = np.empty((P, len(sel)), dtype=np.float64)
    min_dd = np.zeros(P, dtype=np.float64)
    c = float(monthly_contribution)
    keep = None
    if no_contrib is not None and np.asarray(no_contrib).any():
        nc = np.asarray(no_contrib, dtype=bool)
        keep = (~nc).astype(dtype)
        cash_idx = int(np.where(nc)[0][0])
    for ps in range(0, P, chunk):
        pe = min(P, ps + chunk)
        n = pe - ps
        a = np.tile(v0, (n, 1))
        total0 = a.sum(axis=1)
        peak = total0.astype(np.float64)
        dd = np.zeros(n)
        values[ps:pe, 0] = total0
        day = 0
        while day < D:
            end = min(day + step, D)
            g = logr[idx[ps:pe, day:end]]          # (n, L, N)
            np.cumsum(g, axis=1, out=g)
            np.exp(g, out=g)
            g *= a[:, None, :]
            vals = g.sum(axis=2, dtype=np.float64)  # (n, L)
            run = np.maximum(peak[:, None], np.maximum.accumulate(vals, axis=1))
            dd = np.minimum(dd, (vals / run - 1.0).min(axis=1))
            peak = run[:, -1]
            a = g[:, -1, :]
            if c > 0 and end - day == step:
                tot = vals[:, -1]
                factor = 1.0 + c / tot
                if keep is None:
                    a = a * factor[:, None].astype(dtype)
                else:
                    am = a * keep
                    risky = am.sum(axis=1)
                    pos = risky > 0
                    a = a.copy()
                    a[pos] += (am[pos] * (c / risky[pos])[:, None]).astype(dtype)
                    a[~pos, cash_idx] += c
                vals[:, -1] = tot + c
                peak = peak * factor
            lo, hi = np.searchsorted(sel, [day + 1, end + 1])
            if hi > lo:
                values[ps:pe, lo:hi] = vals[:, sel[lo:hi] - day - 1]
            day = end
        min_dd[ps:pe] = dd
    return {"days": sel, "values": values, "min_drawdown": min_dd}


def summarize(sim: dict, start_value: float, total_contributions: float) -> dict:
    vals = sim["values"]
    pct = np.percentile(vals, PCTS, axis=0)  # (5, points)
    percentiles = [
        {"day": int(d), **{f"p{p}": round(float(pct[i, j]), 2) for i, p in enumerate(PCTS)}}
        for j, d in enumerate(sim["days"])
    ]
    final = vals[:, -1]
    fp = np.percentile(final, PCTS)
    return {
        "start_value": round(float(start_value), 2),
        "total_contributions": round(float(total_contributions), 2),
        "percentiles": percentiles,
        "final": {**{f"p{p}": round(float(fp[i]), 2) for i, p in enumerate(PCTS)},
                  "mean": round(float(final.mean()), 2)},
        "prob_loss": round(float((final < (start_value + total_contributions) * (1 - 1e-6)).mean()), 4),
        "prob_drawdown_20": round(float((sim["min_drawdown"] <= -0.2).mean()), 4),
    }


def n_contributions(days: int, step: int = CONTRIBUTION_STEP) -> int:
    return days // step

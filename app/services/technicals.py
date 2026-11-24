"""Pure technical-indicator maths (pandas/numpy only, no I/O)."""
from typing import List

import numpy as np
import pandas as pd


def sma(close: pd.Series, window: int) -> pd.Series:
    """Simple moving average of the last `window` values (NaN until a full window)."""
    return close.rolling(window, min_periods=window).mean()


def ema(close: pd.Series, span: int) -> pd.Series:
    """Exponential moving average, alpha = 2/(span+1), ewm(adjust=False), seeded with the first value."""
    return close.ewm(span=span, adjust=False).mean()


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """Wilder RSI: gains/losses smoothed with alpha=1/window (ewm adjust=False).

    RSI = 100 - 100/(1+RS), RS = avg_gain/avg_loss; RSI = 100 when avg_loss == 0.
    The first `window` values are NaN (the first diff is undefined and a warm-up
    of `window` changes is required).
    """
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    # first diff is NaN: start smoothing from the second observation
    avg_gain = gain.iloc[1:].ewm(alpha=1.0 / window, adjust=False).mean().reindex(close.index)
    avg_loss = loss.iloc[1:].ewm(alpha=1.0 / window, adjust=False).mean().reindex(close.index)
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - 100.0 / (1.0 + rs)
    out = out.where(avg_loss != 0.0, 100.0)
    out = out.where(avg_gain.notna())
    out.iloc[:window] = np.nan
    return out


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """MACD = EMA(fast) - EMA(slow); signal = EMA(signal) of MACD; hist = MACD - signal."""
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return pd.DataFrame({"macd": line, "macd_signal": sig, "macd_hist": line - sig})


def bollinger(close: pd.Series, window: int = 20, k: float = 2.0) -> pd.DataFrame:
    """Bollinger bands: middle = SMA(window), upper/lower = middle +/- k * population std (ddof=0)."""
    mid = sma(close, window)
    sd = close.rolling(window, min_periods=window).std(ddof=0)
    return pd.DataFrame({"bb_upper": mid + k * sd, "bb_middle": mid, "bb_lower": mid - k * sd})


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all indicator columns (lowercase names) to an OHLCV frame (Open..Volume)."""
    close = df["Close"]
    out = pd.DataFrame(index=df.index)
    for c in ("Open", "High", "Low", "Close", "Volume"):
        out[c.lower()] = df[c]
    out["sma20"] = sma(close, 20)
    out["sma50"] = sma(close, 50)
    out["sma200"] = sma(close, 200)
    out["ema12"] = ema(close, 12)
    out["ema26"] = ema(close, 26)
    out["rsi14"] = rsi(close, 14)
    out = out.join(macd(close)).join(bollinger(close))
    return out


def recent_cross(fast: pd.Series, slow: pd.Series, sessions: int = 20) -> dict:
    """Detect a fast/slow cross within the last `sessions` sessions.

    golden: fast <= slow on one session and fast > slow on the next.
    death: fast >= slow then fast < slow.
    """
    diff = (fast - slow).dropna()
    if len(diff) < 2:
        return {"golden": False, "death": False}
    prev = diff.shift(1)
    golden = ((prev <= 0) & (diff > 0)).iloc[-sessions:]
    death = ((prev >= 0) & (diff < 0)).iloc[-sessions:]
    return {"golden": bool(golden.any()), "death": bool(death.any())}


def _cluster(prices: List[float], tol: float = 0.015) -> List[float]:
    clusters: List[List[float]] = []
    for p in sorted(prices):
        if clusters and p <= np.mean(clusters[-1]) * (1 + tol):
            clusters[-1].append(p)
        else:
            clusters.append([p])
    return [float(np.mean(c)) for c in clusters]


def support_resistance(close: pd.Series, window: int = 5, tol: float = 0.015, max_levels: int = 3) -> dict:
    """Simple levels from local extrema of close.

    A point is a local min/max if it is the min/max of the +/-`window` session
    window (fully inside the series). Extrema are clustered when within `tol`
    (1.5%) of the running cluster mean, and each cluster is averaged. Support =
    clusters below the last close, resistance = above, closest first, max 3.
    """
    c = close.dropna()
    if len(c) < 2 * window + 1:
        return {"support": [], "resistance": []}
    roll_min = c.rolling(2 * window + 1, center=True, min_periods=2 * window + 1).min()
    roll_max = c.rolling(2 * window + 1, center=True, min_periods=2 * window + 1).max()
    lows = c[(c == roll_min)].tolist()
    highs = c[(c == roll_max)].tolist()
    last = float(c.iloc[-1])
    levels = _cluster(lows + highs, tol)
    support = sorted([l for l in levels if l < last], key=lambda x: last - x)[:max_levels]
    resistance = sorted([l for l in levels if l > last], key=lambda x: x - last)[:max_levels]
    return {"support": [round(x, 4) for x in support], "resistance": [round(x, 4) for x in resistance]}

"""Pure maths for the market context endpoint (no I/O)."""
from typing import Optional

import pandas as pd

WINDOW = 252


def percentile_rank(series: pd.Series, window: int = WINDOW) -> Optional[float]:
    """Mid-rank percentile (0-100): share of the other values in the last `window` below the latest, plus half of the ties.

    Min of the window -> small value (1/n*100 if unique); we use the mean of
    strict-below and at-or-below shares (mid-rank) so that the minimum maps to 0
    and the maximum to 100 for unique values, and ties land in the middle.
    """
    s = series.dropna().tail(window)
    n = len(s)
    if n < 2:
        return None
    last = s.iloc[-1]
    below = float((s < last).sum())
    equal = float((s == last).sum())  # includes the last value itself
    # mid-rank over the other n-1 observations
    rank = below + (equal - 1) / 2.0
    return round(100.0 * rank / (n - 1), 1)


def sma_distance(series: pd.Series, window: int) -> Optional[float]:
    """Percent distance of the last value to its `window`-day SMA."""
    s = series.dropna()
    if len(s) < window:
        return None
    sma = float(s.tail(window).mean())
    if sma == 0:
        return None
    return round((float(s.iloc[-1]) / sma - 1) * 100, 2)


def change_1d(series: pd.Series, absolute: bool = False) -> Optional[float]:
    s = series.dropna()
    if len(s) < 2 or (not absolute and s.iloc[-2] == 0):
        return None
    if absolute:
        return round(float(s.iloc[-1] - s.iloc[-2]), 3)
    return round((float(s.iloc[-1]) / float(s.iloc[-2]) - 1) * 100, 2)


def describe_percentile(label: str, pct: Optional[float]) -> Optional[str]:
    if pct is None:
        return None
    return f"{label} is higher than on {pct:.0f}% of days in the past year."

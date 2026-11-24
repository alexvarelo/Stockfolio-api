"""Fetches market indicators (cached 15 min) and assembles the context response."""
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, Optional

import pandas as pd
import yfinance as yf

from app.core.cache import TTLCacheBackend, CacheBackend
from app.models.market import MarketContextResponse, MarketIndicator, SmaDistance
from app.services import market_context as mc

logger = logging.getLogger(__name__)

MARKET_TTL = 15 * 60

INDICATORS = [
    # key, label, symbol, unit
    ("vix", "VIX (volatility index)", "^VIX", "index"),
    ("us10y", "US 10-year Treasury yield", "^TNX", "percent"),
    ("dxy", "US Dollar index", "DX-Y.NYB", "index"),
    ("sp500", "S&P 500", "^GSPC", "index"),
]

BREADTH_NOTE = (
    "Market breadth (% of S&P 500 members above their 200-day average) is not available: "
    "it needs a batched download of ~500 tickers and a maintained constituent list."
)

market_cache: CacheBackend = TTLCacheBackend(MARKET_TTL, maxsize=8)


def fetch_closes(symbol: str) -> pd.Series:
    """2y of daily closes (enough for 1y percentile plus a 200-day SMA)."""
    hist = yf.Ticker(symbol).history(period="2y", auto_adjust=False)
    if hist is None or hist.empty or "Close" not in hist:
        raise ValueError(f"no data for {symbol}")
    close = hist["Close"].dropna()
    if close.index.tz is not None:
        close.index = close.index.tz_localize(None)
    close.index = close.index.normalize()
    return close


def build_indicator(key: str, label: str, symbol: str, unit: str, closes: pd.Series) -> MarketIndicator:
    value = round(float(closes.iloc[-1]), 2)
    pct = mc.percentile_rank(closes)
    extra = None
    if key == "sp500":
        extra = SmaDistance(
            sma50_distance=mc.sma_distance(closes, 50),
            sma200_distance=mc.sma_distance(closes, 200),
        )
    return MarketIndicator(
        key=key, label=label, symbol=symbol, unit=unit, value=value,
        change_1d=mc.change_1d(closes, absolute=(unit == "percent")),
        percentile_1y=pct,
        sparkline=[round(float(v), 2) for v in closes.tail(60)],
        extra=extra,
        reading=mc.describe_percentile(label, pct),
    )


def compute_market_context(fetcher: Callable[[str], pd.Series] = fetch_closes) -> MarketContextResponse:
    def one(spec):
        try:
            return fetcher(spec[2])
        except Exception as e:  # one failing symbol must not fail the endpoint
            logger.warning("market context: %s failed: %s", spec[2], e)
            return None

    with ThreadPoolExecutor(max_workers=len(INDICATORS)) as pool:
        results = list(pool.map(one, INDICATORS))

    indicators, notes, dates = [], [], []
    for (key, label, symbol, unit), closes in zip(INDICATORS, results):
        if closes is None or len(closes.dropna()) == 0:
            indicators.append(MarketIndicator(key=key, label=label, symbol=symbol, unit=unit))
            notes.append(f"{label} ({symbol}) is temporarily unavailable.")
            continue
        closes = closes.dropna()
        dates.append(closes.index[-1])
        indicators.append(build_indicator(key, label, symbol, unit, closes))
    notes.append(BREADTH_NOTE)
    return MarketContextResponse(
        as_of=max(dates).strftime("%Y-%m-%d") if dates else None,
        indicators=indicators, breadth=None, notes=notes,
    )


def get_market_context(fetcher: Optional[Callable[[str], pd.Series]] = None) -> MarketContextResponse:
    """Cached for 15 min. Responses with failed indicators are not cached."""
    cached = market_cache.get("context")
    if cached is not None:
        return cached
    result = compute_market_context(fetcher or fetch_closes)
    if all(i.value is not None for i in result.indicators):
        market_cache.set("context", result)
    return result

"""Fetch OHLCV (cached) and assemble the technicals response."""
import math
from typing import Any, Optional

import pandas as pd

from app.models.technicals import (
    TechnicalLatest, TechnicalLevels, TechnicalPoint, TechnicalsResponse,
)
from app.services import technicals as ta

# requested period -> (fetch period with warm-up, calendar days to keep)
FETCH_PERIOD = {"6mo": "2y", "1y": "2y", "2y": "5y", "5y": "max"}
KEEP_DAYS = {"6mo": 183, "1y": 365, "2y": 730, "5y": 1826}
DISCLAIMER = "Educational information, not financial advice."


def _num(v: Any) -> Optional[float]:
    """NaN/inf/None -> None, else float."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def build_technicals(ticker: str, period: str, df: pd.DataFrame, currency: Optional[str]) -> TechnicalsResponse:
    ind = ta.compute_indicators(df)
    cross = ta.recent_cross(ind["sma50"], ind["sma200"], 20)
    vol = ind["volume"]
    avg20 = _num(vol.tail(20).mean()) if len(vol) >= 20 else None
    avg50 = _num(vol.tail(50).mean()) if len(vol) >= 50 else None

    end = ind.index[-1]
    trimmed = ind[ind.index > end - pd.Timedelta(days=KEEP_DAYS[period])]
    if trimmed.empty:
        trimmed = ind.tail(1)

    series = []
    for ts, row in trimmed.iterrows():
        d = {k: _num(v) for k, v in row.items()}
        series.append(TechnicalPoint(date=ts.strftime("%Y-%m-%d"), **d))

    last = ind.iloc[-1]
    close, s50, s200 = _num(last["close"]), _num(last["sma50"]), _num(last["sma200"])
    latest = TechnicalLatest(
        close=close,
        rsi14=_num(last["rsi14"]),
        macd=_num(last["macd"]),
        macd_signal=_num(last["macd_signal"]),
        sma50=s50,
        sma200=s200,
        above_sma50=(close > s50) if close is not None and s50 is not None else None,
        above_sma200=(close > s200) if close is not None and s200 is not None else None,
        golden_cross_recent=cross["golden"],
        death_cross_recent=cross["death"],
        avg_volume_20=avg20,
        avg_volume_50=avg50,
    )
    lv = ta.support_resistance(trimmed["close"])
    return TechnicalsResponse(
        ticker=ticker,
        period=period,
        currency=currency,
        as_of=trimmed.index[-1].strftime("%Y-%m-%d"),
        series=series,
        latest=latest,
        levels=TechnicalLevels(**lv),
        disclaimer=DISCLAIMER,
    )


def get_technicals(yf_service, ticker: str, period: str) -> TechnicalsResponse:
    ticker = ticker.upper()
    df = yf_service.get_daily_ohlcv(ticker, FETCH_PERIOD[period])
    currency = yf_service.get_currency(ticker)
    return build_technicals(ticker, period, df, currency)

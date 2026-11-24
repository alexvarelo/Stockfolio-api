from typing import List, Optional
from pydantic import BaseModel


class TechnicalPoint(BaseModel):
    date: str
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[float] = None
    sma20: Optional[float] = None
    sma50: Optional[float] = None
    sma200: Optional[float] = None
    ema12: Optional[float] = None
    ema26: Optional[float] = None
    rsi14: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_middle: Optional[float] = None
    bb_lower: Optional[float] = None


class TechnicalLatest(BaseModel):
    close: Optional[float] = None
    rsi14: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    sma50: Optional[float] = None
    sma200: Optional[float] = None
    above_sma50: Optional[bool] = None
    above_sma200: Optional[bool] = None
    golden_cross_recent: bool = False
    death_cross_recent: bool = False
    avg_volume_20: Optional[float] = None
    avg_volume_50: Optional[float] = None


class TechnicalLevels(BaseModel):
    support: List[float] = []
    resistance: List[float] = []


class TechnicalsResponse(BaseModel):
    ticker: str
    period: str
    currency: Optional[str] = None
    as_of: Optional[str] = None
    series: List[TechnicalPoint]
    latest: TechnicalLatest
    levels: TechnicalLevels
    disclaimer: str = "Educational information, not financial advice."

from typing import List, Optional

from pydantic import BaseModel, Field

DISCLAIMER = "Educational information, not financial advice."


class SmaDistance(BaseModel):
    sma50_distance: Optional[float] = Field(None, description="Percent distance of the last close to its 50-day SMA")
    sma200_distance: Optional[float] = Field(None, description="Percent distance of the last close to its 200-day SMA")


class MarketIndicator(BaseModel):
    key: str = Field(..., description="vix | us10y | dxy | sp500")
    label: str
    symbol: str
    unit: str = Field(..., description="index | percent")
    description: Optional[str] = Field(None, description="Static plain-language description of the indicator")
    as_of: Optional[str] = Field(None, description="Date (YYYY-MM-DD) of this indicator's last close")
    value: Optional[float] = None
    change_1d: Optional[float] = Field(None, description="Percent change vs previous close (for us10y: change in percentage points)")
    percentile_1y: Optional[float] = Field(None, description="0-100 mid-rank percentile over the last ~252 sessions: share of other sessions below today's value plus half of those equal to it")
    sparkline: List[float] = Field(default_factory=list, description="Last ~60 closes")
    extra: Optional[SmaDistance] = None
    reading: Optional[str] = Field(None, description="Neutral, purely descriptive sentence")


class MarketBreadth(BaseModel):
    pct_above_sma200: float
    percentile_1y: Optional[float] = None


class MarketContextResponse(BaseModel):
    as_of: Optional[str] = Field(None, description="Date (YYYY-MM-DD) of the latest data point")
    indicators: List[MarketIndicator]
    breadth: Optional[MarketBreadth] = None
    notes: List[str] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER

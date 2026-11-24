"""Request/response models for POST /strategies/backtest."""
from datetime import date as _date
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.schemas import MAX_MONEY, TICKER_PATTERN, check_base_currency

Strategy = Literal["dca", "rebalance", "rsi", "ma_cross"]
MIN_START = _date(2000, 1, 1)
MIN_SPAN_DAYS = 180


class BacktestTicker(BaseModel):
    ticker: str = Field(..., pattern=TICKER_PATTERN)
    weight: float = Field(..., gt=0, description="Relative weight; weights are normalised to sum to 1")

    @field_validator("ticker")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class BacktestParams(BaseModel):
    monthly_amount: float = Field(0.0, ge=0, le=MAX_MONEY, description="dca: amount invested on the first trading day of each month")
    rebalance_frequency: Literal["monthly", "quarterly", "yearly"] = "quarterly"
    rsi_buy: float = Field(30.0, gt=0, lt=100, description="rsi: buy when RSI(14) crosses below this level")
    rsi_sell: float = Field(70.0, gt=0, lt=100, description="rsi: sell when RSI(14) crosses above this level")
    fast: int = Field(50, ge=2, le=400, description="ma_cross: fast SMA window")
    slow: int = Field(200, ge=3, le=600, description="ma_cross: slow SMA window")


class BacktestRequest(BaseModel):
    strategy: Strategy
    tickers: List[BacktestTicker] = Field(..., min_length=1, max_length=15)
    start_date: _date
    end_date: _date
    initial_capital: float = Field(0.0, ge=0, le=MAX_MONEY)
    base_currency: str = Field("USD", pattern=r"^[A-Za-z]{3}$")
    params: BacktestParams = Field(default_factory=BacktestParams)
    fee_bps: float = Field(0.0, ge=0, le=100, description="Fee per trade in basis points of traded notional")

    @field_validator("base_currency")
    @classmethod
    def _upper_currency(cls, v: str) -> str:
        return check_base_currency(v)

    @model_validator(mode="after")
    def _check(self):
        if self.start_date < MIN_START:
            raise ValueError("start_date must be on or after 2000-01-01")
        if self.end_date > _date.today():
            raise ValueError("end_date cannot be in the future")
        if (self.end_date - self.start_date).days < MIN_SPAN_DAYS:
            raise ValueError(f"end_date must be at least {MIN_SPAN_DAYS} days after start_date")
        names = [t.ticker for t in self.tickers]
        if len(set(names)) != len(names):
            raise ValueError("duplicate tickers")
        if self.strategy in ("rsi", "ma_cross") and len(names) != 1:
            raise ValueError(f"strategy '{self.strategy}' requires exactly 1 ticker")
        p = self.params
        if self.strategy == "dca":
            if self.initial_capital <= 0 and p.monthly_amount <= 0:
                raise ValueError("dca needs initial_capital > 0 or params.monthly_amount > 0")
        elif self.initial_capital <= 0:
            raise ValueError(f"strategy '{self.strategy}' requires initial_capital > 0")
        if self.strategy == "rsi" and p.rsi_buy >= p.rsi_sell:
            raise ValueError("rsi_buy must be lower than rsi_sell")
        if self.strategy == "ma_cross" and p.fast >= p.slow:
            raise ValueError("fast must be lower than slow")
        return self


class EquityPoint(BaseModel):
    date: _date
    strategy_value: float
    benchmark_value: float
    invested: float = Field(..., description="Cumulative external cash contributed up to this date")


class BacktestMetrics(BaseModel):
    final_value: float
    total_invested: float
    total_return: float = Field(..., description="final_value / total_invested - 1 (money-in vs money-out)")
    cagr: Optional[float] = Field(None, description=(
        "Time-weighted annualised return: daily returns chained excluding external cash flows, "
        "annualised over calendar days (365.25). Not money-weighted."))
    max_drawdown: Optional[float] = Field(None, description=(
        "Most negative peak-to-trough fraction of the time-weighted return index (unaffected by contributions)"))
    volatility_annual: Optional[float] = Field(None, description="Std of daily time-weighted returns * sqrt(252)")
    trades: int
    time_in_market: float = Field(..., description="Fraction of days with a non-zero invested position")


class BacktestTrade(BaseModel):
    date: _date
    ticker: str
    side: Literal["buy", "sell"]
    quantity: float
    price: float = Field(..., description="Close in base currency")


class BacktestMetricsPair(BaseModel):
    strategy: BacktestMetrics
    benchmark: BacktestMetrics


class BacktestResponse(BaseModel):
    strategy: Strategy
    base_currency: str
    start_date: _date = Field(..., description="First simulated trading day")
    end_date: _date = Field(..., description="Last simulated trading day")
    equity_curve: List[EquityPoint]
    metrics: BacktestMetricsPair
    trades: List[BacktestTrade] = Field(..., description="Most recent 200 strategy trades")
    notes: List[str]
    disclaimer: str = "Educational information, not financial advice."

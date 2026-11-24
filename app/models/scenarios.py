"""Request/response models for /scenarios endpoints."""
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.schemas import (
    MAX_MONEY, MAX_QUANTITY, PortfolioPositionInput, TICKER_PATTERN, check_base_currency,
)

DISCLAIMER = "Educational information, not financial advice."


class ScenarioPortfolioRequest(BaseModel):
    positions: List[PortfolioPositionInput] = Field(..., min_length=1, max_length=50)
    base_currency: str = Field("USD", pattern=r"^[A-Za-z]{3}$")

    @field_validator("base_currency")
    @classmethod
    def _upper_currency(cls, v: str) -> str:
        return check_base_currency(v)


class ScenarioExcluded(BaseModel):
    ticker: str
    reason: Literal["no_history", "no_fx", "unknown_currency", "short_history", "invalid_prices"]


# ---- Stress ----
class StressRequest(ScenarioPortfolioRequest):
    shocks: List[float] = Field(default_factory=lambda: [-0.1, -0.2, -0.3], max_length=10,
                                description="Market shocks as decimals (-0.2 = -20%)")

    @field_validator("shocks")
    @classmethod
    def _check_shocks(cls, v: List[float]) -> List[float]:
        if any(s <= -1.0 or s > 1.0 for s in v):
            raise ValueError("shocks must be within (-1, 1]")
        seen, out = set(), []
        for s in v:  # de-duplicate (scenario keys use the shock rounded to 0.01%)
            k = round(s, 4)
            if k not in seen:
                seen.add(k)
                out.append(s)
        return out


class StressPosition(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    ticker: str
    ret: float = Field(..., alias="return", description="Position return in the scenario (decimal, base currency)")
    method: Literal["historical", "beta_proxy", "shock"]
    weight: float = Field(..., description="Current weight in the portfolio (0-1)")
    beta: Optional[float] = Field(
        None, description="Beta (clamped to [0, 3]) used for beta_proxy/shock; null for 'historical' positions. "
                          "Estimated from weekly (W-FRI) base-currency returns vs ^GSPC over the last 2y "
                          "(>= 52 weekly observations), else 1.0")


class StressScenario(BaseModel):
    key: str
    label: str
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    method: Literal["historical", "beta_proxy", "shock"] = Field(
        ..., description="'historical' if every position has its own data; 'beta_proxy' if any position "
                         "used beta x benchmark; 'shock' for market shocks")
    portfolio_return: float
    value_after: float
    pnl: float
    positions: List[StressPosition]
    benchmark_return: float


class StressResponse(BaseModel):
    base_currency: str
    current_value: float
    scenarios: List[StressScenario]
    excluded: List[ScenarioExcluded] = []
    disclaimer: str = DISCLAIMER


# ---- Monte Carlo ----
class MonteCarloRequest(ScenarioPortfolioRequest):
    horizon_years: int = Field(1, ge=1, le=5)
    paths: int = Field(5000, ge=1000, le=10000)
    monthly_contribution: float = Field(0.0, ge=0, le=MAX_MONEY, description="Added every 21 trading days, in base currency")
    lookback: Literal["3y", "5y", "10y"] = "5y"
    seed: Optional[int] = Field(None, ge=0, le=2**32 - 1, description="RNG seed (default 42)")


class PercentilePoint(BaseModel):
    day: int
    p5: float
    p25: float
    p50: float
    p75: float
    p95: float


class FinalDistribution(BaseModel):
    p5: float
    p25: float
    p50: float
    p75: float
    p95: float
    mean: float


class MonteCarloSummary(BaseModel):
    start_value: float
    total_contributions: float
    percentiles: List[PercentilePoint]
    final: FinalDistribution
    prob_loss: float = Field(..., description="Share of paths ending below start value + total contributions")
    prob_drawdown_20: float = Field(..., description="Share of paths with max drawdown <= -20%")


class MonteCarloResponse(MonteCarloSummary):
    base_currency: str
    horizon_years: int
    paths: int
    seed: int
    lookback_used: str
    observations: int
    excluded: List[ScenarioExcluded] = []
    disclaimer: str = DISCLAIMER


# ---- What-if ----
class WhatIfTrade(BaseModel):
    ticker: str = Field(..., pattern=TICKER_PATTERN)
    quantity: float = Field(..., gt=0, le=MAX_QUANTITY)


class WhatIfChanges(BaseModel):
    sell: List[WhatIfTrade] = Field(default_factory=list, max_length=50)
    buy: List[WhatIfTrade] = Field(default_factory=list, max_length=50)
    monthly_contribution: Optional[float] = Field(
        None, ge=0, le=MAX_MONEY, description="Contribution of the modified portfolio (defaults to the current one)")


MAX_WHATIF_PATHS = 5000


class WhatIfRequest(BaseModel):
    current: MonteCarloRequest
    changes: WhatIfChanges

    @model_validator(mode="after")
    def _cap_paths(self):
        if self.current.paths > MAX_WHATIF_PATHS:
            raise ValueError(f"what-if supports at most {MAX_WHATIF_PATHS} paths")
        return self


class WhatIfDelta(BaseModel):
    p50: float
    p5: float
    prob_loss: float
    p50_return: Optional[float] = Field(
        None, description="Modified minus current of (final p50 / (start_value + total_contributions) - 1)")
    p5_return: Optional[float] = Field(
        None, description="Modified minus current of (final p5 / (start_value + total_contributions) - 1)")


class RiskSnapshot(BaseModel):
    volatility_annual: Optional[float] = None
    beta: Optional[float] = None
    max_drawdown: Optional[float] = None
    hhi: float


class WhatIfResponse(BaseModel):
    base_currency: str
    horizon_years: int
    paths: int
    seed: int
    lookback_used: str
    observations: int
    current: MonteCarloSummary
    modified: MonteCarloSummary
    delta: WhatIfDelta
    cash_from_sales: float = Field(
        0.0, description="Proceeds of the sells (qty x last price, base currency). Kept as cash with 0 return "
                         "in the modified portfolio (included in its start_value); buys are funded by new money")
    risk_current: RiskSnapshot
    risk_modified: RiskSnapshot
    excluded: List[ScenarioExcluded] = []
    disclaimer: str = DISCLAIMER

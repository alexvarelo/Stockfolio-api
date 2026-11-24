"""Pydantic models for company analysis endpoints (financials, health, compare)."""
from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

DISCLAIMER = "Educational information, not financial advice."


class FinancialItem(BaseModel):
    period_end: date
    revenue: Optional[float] = None
    gross_profit: Optional[float] = None
    operating_income: Optional[float] = None
    net_income: Optional[float] = None
    gross_margin: Optional[float] = Field(None, description="Decimal, e.g. 0.42")
    operating_margin: Optional[float] = None
    net_margin: Optional[float] = None
    operating_cash_flow: Optional[float] = None
    capex: Optional[float] = None
    free_cash_flow: Optional[float] = Field(None, description="Operating cash flow minus |capex|")
    cash: Optional[float] = Field(None, description="Cash plus short-term investments")
    total_debt: Optional[float] = None
    net_debt: Optional[float] = Field(None, description="Total debt minus cash")
    shares_outstanding: Optional[float] = None
    ebitda: Optional[float] = None


class FinancialsResponse(BaseModel):
    ticker: str
    currency: Optional[str] = Field(None, description="Financial statement currency (may differ from quote currency)")
    period: Literal["annual", "quarterly"]
    items: List[FinancialItem]
    disclaimer: str = DISCLAIMER


class HealthMetric(BaseModel):
    key: str
    label: str
    value: Optional[float] = Field(None, description="Number in `unit`; for 'percent' it is percentage points (3.2 = 3.2%)")
    unit: Literal["months", "ratio", "percent", "score", "x"]
    status: Literal["good", "warn", "bad", "na"]
    explanation: str


class HealthResponse(BaseModel):
    ticker: str
    as_of: date = Field(..., description="Latest financial statement period end used")
    metrics: List[HealthMetric]
    disclaimer: str = DISCLAIMER


class CompareValuation(BaseModel):
    pe: Optional[float] = None
    forward_pe: Optional[float] = None
    peg: Optional[float] = None
    ev_ebitda: Optional[float] = None
    price_to_sales: Optional[float] = None
    price_to_book: Optional[float] = None


class CompareGrowth(BaseModel):
    revenue_growth_yoy: Optional[float] = None
    earnings_growth_yoy: Optional[float] = None


class CompareMargins(BaseModel):
    gross: Optional[float] = None
    operating: Optional[float] = None
    net: Optional[float] = None


class CompareHealth(BaseModel):
    net_debt_to_ebitda: Optional[float] = None
    current_ratio: Optional[float] = None
    altman_z: Optional[float] = None


class CompareReturns(BaseModel):
    r1y: Optional[float] = Field(None, description="Total price return, decimal")
    r3y: Optional[float] = None
    r5y: Optional[float] = None


class CompareRow(BaseModel):
    ticker: str
    name: Optional[str] = None
    currency: Optional[str] = None
    price: Optional[float] = None
    market_cap: Optional[float] = None
    market_cap_usd: Optional[float] = None
    valuation: CompareValuation
    growth: CompareGrowth
    margins: CompareMargins
    health: CompareHealth
    returns: CompareReturns


class CompareResponse(BaseModel):
    tickers: List[str]
    base_currency: str = "USD"
    rows: List[CompareRow]
    missing: List[str]
    disclaimer: str = DISCLAIMER

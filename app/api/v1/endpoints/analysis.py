import re
from typing import Any, Dict, List, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.core.dependencies import get_current_client
from app.models.analysis import CompareResponse, FinancialsResponse, HealthResponse
from app.models.schemas import ErrorResponse
from app.services import fundamentals_service
from app.services.yfinance_service import YFinanceService, yfinance_service_singleton

router = APIRouter()

TICKER_PATTERN = r"^[A-Za-z0-9.^=\-]{1,20}$"
_TICKER_RE = re.compile(TICKER_PATTERN)

_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Unauthorized"},
    404: {"model": ErrorResponse, "description": "Ticker not found"},
    422: {"description": "Invalid parameters"},
}


def get_yfinance_service() -> YFinanceService:
    return yfinance_service_singleton


@router.get("/stock/{ticker}/financials", response_model=FinancialsResponse, responses=_RESPONSES,
            summary="Financial statements summary",
            description="Last 5 annual or 8 quarterly periods (oldest first). Amounts are in the "
                        "statement `currency`; margins are decimals. Educational information, not financial advice.")
def get_financials(
    ticker: str = Path(..., pattern=TICKER_PATTERN),
    period: Literal["annual", "quarterly"] = Query("annual"),
    client: Dict[str, Any] = Depends(get_current_client),
) -> FinancialsResponse:
    return fundamentals_service.get_financials(ticker, period)


@router.get("/stock/{ticker}/health", response_model=HealthResponse, responses=_RESPONSES,
            summary="Financial health indicators",
            description="Cash runway, dilution, leverage, interest coverage, Altman Z and Piotroski F, each "
                        "with a status. Educational information, not financial advice.")
def get_health(
    ticker: str = Path(..., pattern=TICKER_PATTERN),
    client: Dict[str, Any] = Depends(get_current_client),
    service: YFinanceService = Depends(get_yfinance_service),
) -> HealthResponse:
    return fundamentals_service.get_health(ticker, service)


@router.get("/compare", response_model=CompareResponse, responses=_RESPONSES,
            summary="Compare 2-6 tickers",
            description="Normalised valuation, growth, margins, health and 1/3/5y price returns (decimals). "
                        "Educational information, not financial advice.")
def compare(
    tickers: str = Query(..., description="Comma separated, 2-6 tickers"),
    client: Dict[str, Any] = Depends(get_current_client),
    service: YFinanceService = Depends(get_yfinance_service),
) -> CompareResponse:
    seen: List[str] = []
    for raw in tickers.split(","):
        t = raw.strip().upper()
        if not t:
            continue
        if not _TICKER_RE.match(t):
            raise HTTPException(status_code=422, detail=f"Invalid ticker: {raw.strip()!r}")
        if t not in seen:
            seen.append(t)
    if not 2 <= len(seen) <= 6:
        raise HTTPException(status_code=422, detail="Provide between 2 and 6 distinct tickers")
    return fundamentals_service.compute_compare(seen, service)

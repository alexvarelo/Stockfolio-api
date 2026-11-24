from fastapi import APIRouter, Depends
from typing import Any, Dict

from app.core.dependencies import get_current_client
from app.models.schemas import PortfolioRiskRequest, PortfolioRiskResponse, ErrorResponse
from app.services.yfinance_service import YFinanceService, yfinance_service_singleton
from app.services.portfolio_risk_service import compute_portfolio_risk

router = APIRouter()


def get_yfinance_service() -> YFinanceService:
    return yfinance_service_singleton


@router.post(
    "/portfolio/risk",
    response_model=PortfolioRiskResponse,
    summary="Portfolio risk metrics",
    description=(
        "Beta vs a benchmark, annualised volatility, max drawdown, Sharpe ratio, concentration "
        "(largest position, HHI) and correlation matrix for a buy-and-hold portfolio of the given "
        "positions. All ratios are decimals. Educational information, not financial advice."
    ),
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        422: {"description": "Invalid request or no usable price data"},
    },
)
def portfolio_risk(
    request: PortfolioRiskRequest,
    client: Dict[str, Any] = Depends(get_current_client),
    service: YFinanceService = Depends(get_yfinance_service),
) -> PortfolioRiskResponse:
    return compute_portfolio_risk(request, service)

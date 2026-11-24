from typing import Any, Dict

from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_client
from app.models.schemas import ErrorResponse
from app.models.strategies import BacktestRequest, BacktestResponse
from app.services.backtest_service import run_strategy_backtest
from app.services.yfinance_service import YFinanceService, yfinance_service_singleton

router = APIRouter()


def get_yfinance_service() -> YFinanceService:
    return yfinance_service_singleton


@router.post(
    "/strategies/backtest",
    response_model=BacktestResponse,
    summary="Backtest a predefined strategy",
    description=(
        "Backtests DCA, periodic rebalancing, RSI or SMA-cross strategies against a buy-and-hold "
        "benchmark with the same cash flows. Trades at daily closes in base currency; signals "
        "execute the next day. Educational information, not financial advice."
    ),
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        422: {"description": "Invalid request or missing price data"},
    },
)
def backtest_strategy(
    request: BacktestRequest,
    client: Dict[str, Any] = Depends(get_current_client),
    service: YFinanceService = Depends(get_yfinance_service),
) -> BacktestResponse:
    return run_strategy_backtest(request, service)

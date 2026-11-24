from typing import Any, Dict

from fastapi import APIRouter, Depends

from app.api.v1.endpoints.portfolio import get_yfinance_service
from app.core.dependencies import get_current_client
from app.models.schemas import ErrorResponse
from app.models.scenarios import (
    StressRequest, StressResponse, MonteCarloRequest, MonteCarloResponse, WhatIfRequest, WhatIfResponse,
)
from app.services import scenarios_service
from app.services.yfinance_service import YFinanceService

router = APIRouter()

_RESP = {
    401: {"model": ErrorResponse, "description": "Unauthorized"},
    422: {"description": "Invalid request or no usable price data"},
}


@router.post("/scenarios/stress", response_model=StressResponse, responses=_RESP,
             summary="Stress test a portfolio",
             description="Applies historical crises (2008, COVID 2020, 2022) and market shocks to the "
                         "current positions, using each position's own history or a beta proxy. "
                         "Educational information, not financial advice.")
def stress(request: StressRequest, client: Dict[str, Any] = Depends(get_current_client),
           service: YFinanceService = Depends(get_yfinance_service)) -> StressResponse:
    return scenarios_service.compute_stress(request, service)


@router.post("/scenarios/montecarlo", response_model=MonteCarloResponse, responses=_RESP,
             summary="Monte Carlo projection",
             description="Joint bootstrap of daily returns (keeps correlations); fan-chart percentiles, "
                         "probability of loss and of a 20% drawdown. Educational information, not financial advice.")
def montecarlo(request: MonteCarloRequest, client: Dict[str, Any] = Depends(get_current_client),
               service: YFinanceService = Depends(get_yfinance_service)) -> MonteCarloResponse:
    return scenarios_service.compute_montecarlo(request, service)


@router.post("/scenarios/whatif", response_model=WhatIfResponse, responses=_RESP,
             summary="What-if comparison",
             description="Runs the same Monte Carlo (same seed and bootstrap days) on the current and a "
                         "modified portfolio. Educational information, not financial advice.")
def whatif(request: WhatIfRequest, client: Dict[str, Any] = Depends(get_current_client),
           service: YFinanceService = Depends(get_yfinance_service)) -> WhatIfResponse:
    return scenarios_service.compute_whatif(request, service)

from typing import Any, Dict

from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_client
from app.models.market import MarketContextResponse
from app.models.schemas import ErrorResponse
from app.services import market_context_service

router = APIRouter()


def get_market_context_provider():
    return market_context_service.get_market_context


@router.get(
    "/market/context",
    response_model=MarketContextResponse,
    summary="Market context indicators",
    description=(
        "VIX, US 10y yield (percent), US dollar index and S&P 500 (with distance to its 50/200-day "
        "averages), each with its 1-year percentile (0-100). Cached 15 min. Failed indicators return "
        "null values plus a note. Educational information, not financial advice."
    ),
    responses={401: {"model": ErrorResponse, "description": "Unauthorized"}},
)
def market_context(
    client: Dict[str, Any] = Depends(get_current_client),
    provider=Depends(get_market_context_provider),
) -> MarketContextResponse:
    return provider()

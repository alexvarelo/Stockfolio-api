from typing import Any, Dict, Literal
import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.core.dependencies import get_current_client
from app.core.exceptions import TickerNotFoundError, YFinanceError
from app.models.technicals import TechnicalsResponse
from app.services.technicals_service import get_technicals
from app.services.yfinance_service import YFinanceService, yfinance_service_singleton

logger = logging.getLogger(__name__)

router = APIRouter()


def get_yfinance_service() -> YFinanceService:
    return yfinance_service_singleton


@router.get(
    "/stock/{ticker}/technicals",
    response_model=TechnicalsResponse,
    summary="Technical indicators",
    description="SMA 20/50/200, EMA 12/26, RSI 14, MACD (12,26,9), Bollinger (20,2), average volume and simple support/resistance. Educational information, not financial advice.",
)
def stock_technicals(
    ticker: str = Path(..., pattern=r"^[A-Za-z0-9.^=\-]{1,20}$"),
    period: Literal["6mo", "1y", "2y", "5y"] = Query("1y"),
    yfinance_service: YFinanceService = Depends(get_yfinance_service),
    current_client: Dict[str, Any] = Depends(get_current_client),
) -> TechnicalsResponse:
    try:
        return get_technicals(yfinance_service, ticker, period)
    except TickerNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.detail)
    except YFinanceError as e:
        logger.error(f"YFinance error for {ticker}: {e}")
        raise HTTPException(status_code=503, detail=e.detail)
    except Exception as e:
        logger.error(f"Unexpected error computing technicals for {ticker}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

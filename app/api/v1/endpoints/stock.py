from fastapi import APIRouter, Path, HTTPException, Depends, Query
from typing import Optional
import logging

from app.models.schemas import StockInfo, PriceData, CompanyInfo, ErrorResponse
from app.services.yfinance_service import YFinanceService
from app.core.exceptions import TickerNotFoundError, YFinanceError
from app.core.dependencies import get_current_client
from app.models.database import Client

logger = logging.getLogger(__name__)

router = APIRouter()

def get_yfinance_service() -> YFinanceService:
    """Dependency to get yfinance service instance"""
    return YFinanceService()

@router.get(
    "/stock/{ticker}",
    response_model=StockInfo,
    summary="Get comprehensive stock information",
    description="Get detailed information about a stock including price data and company information",
    responses={
        200: {"description": "Stock information"},
        404: {"model": ErrorResponse, "description": "Ticker not found"},
        503: {"model": ErrorResponse, "description": "YFinance service unavailable"}
    }
)
async def get_stock_info(
    ticker: str = Path(..., description="Stock ticker symbol (e.g., AAPL, MSFT)"),
    yfinance_service: YFinanceService = Depends(get_yfinance_service),
    current_client: Client = Depends(get_current_client)
) -> StockInfo:
    """
    Get comprehensive information about a stock.
    
    This endpoint provides detailed information about a stock including:
    - Current price data (price, volume, market cap, etc.)
    - Company information (name, sector, industry, etc.)
    - Additional financial metrics
    
    - **ticker**: The stock ticker symbol (e.g., AAPL for Apple Inc.)
    
    Returns comprehensive stock information including price data and company details.
    """
    try:
        if not ticker or len(ticker.strip()) == 0:
            raise HTTPException(
                status_code=400,
                detail="Ticker symbol is required"
            )
        
        return yfinance_service.get_stock_info(ticker.strip().upper())
        
    except TickerNotFoundError as e:
        logger.warning(f"Ticker not found: {ticker}")
        raise HTTPException(status_code=404, detail=e.detail)
    except YFinanceError as e:
        logger.error(f"YFinance error for {ticker}: {str(e)}")
        raise HTTPException(status_code=503, detail=e.detail)
    except Exception as e:
        logger.error(f"Unexpected error getting stock info for {ticker}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get(
    "/stock/{ticker}/price",
    response_model=PriceData,
    summary="Get stock price data",
    description="Get current price information for a stock",
    responses={
        200: {"description": "Price data"},
        404: {"model": ErrorResponse, "description": "Ticker not found"},
        503: {"model": ErrorResponse, "description": "YFinance service unavailable"}
    }
)
async def get_stock_price(
    ticker: str = Path(..., description="Stock ticker symbol"),
    yfinance_service: YFinanceService = Depends(get_yfinance_service),
    current_client: Client = Depends(get_current_client)
) -> PriceData:
    """
    Get current price data for a stock.
    
    Returns real-time price information including:
    - Current price
    - Previous close
    - Day's high/low
    - Volume
    - Market cap
    - P/E ratio
    - Dividend yield
    - Price change and percentage
    
    - **ticker**: The stock ticker symbol
    """
    try:
        if not ticker or len(ticker.strip()) == 0:
            raise HTTPException(
                status_code=400,
                detail="Ticker symbol is required"
            )
        
        return yfinance_service.get_price_data(ticker.strip().upper())
        
    except TickerNotFoundError as e:
        logger.warning(f"Ticker not found: {ticker}")
        raise HTTPException(status_code=404, detail=e.detail)
    except YFinanceError as e:
        logger.error(f"YFinance error for {ticker}: {str(e)}")
        raise HTTPException(status_code=503, detail=e.detail)
    except Exception as e:
        logger.error(f"Unexpected error getting price data for {ticker}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get(
    "/stock/{ticker}/info",
    response_model=CompanyInfo,
    summary="Get company information",
    description="Get detailed company information for a stock",
    responses={
        200: {"description": "Company information"},
        404: {"model": ErrorResponse, "description": "Ticker not found"},
        503: {"model": ErrorResponse, "description": "YFinance service unavailable"}
    }
)
async def get_company_info(
    ticker: str = Path(..., description="Stock ticker symbol"),
    yfinance_service: YFinanceService = Depends(get_yfinance_service),
    current_client: Client = Depends(get_current_client)
) -> CompanyInfo:
    """
    Get company information for a stock.
    
    Returns detailed company information including:
    - Company name
    - Sector and industry
    - Country of incorporation
    - Website
    - Company description
    - Number of employees
    - Year founded
    
    - **ticker**: The stock ticker symbol
    """
    try:
        if not ticker or len(ticker.strip()) == 0:
            raise HTTPException(
                status_code=400,
                detail="Ticker symbol is required"
            )
        
        return yfinance_service.get_company_info(ticker.strip().upper())
        
    except TickerNotFoundError as e:
        logger.warning(f"Ticker not found: {ticker}")
        raise HTTPException(status_code=404, detail=e.detail)
    except YFinanceError as e:
        logger.error(f"YFinance error for {ticker}: {str(e)}")
        raise HTTPException(status_code=503, detail=e.detail)
    except Exception as e:
        logger.error(f"Unexpected error getting company info for {ticker}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get(
    "/stock/{ticker}/history",
    summary="Get historical price data",
    description="Get historical price data for a stock",
    responses={
        200: {"description": "Historical data"},
        404: {"model": ErrorResponse, "description": "Ticker not found"},
        503: {"model": ErrorResponse, "description": "YFinance service unavailable"}
    }
)
async def get_historical_data(
    ticker: str = Path(..., description="Stock ticker symbol"),
    period: str = Query("1y", description="Time period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)"),
    yfinance_service: YFinanceService = Depends(get_yfinance_service),
    current_client: Client = Depends(get_current_client)
):
    """
    Get historical price data for a stock.
    
    Returns historical price data in various timeframes.
    
    - **ticker**: The stock ticker symbol
    - **period**: Time period for historical data
        - 1d, 5d: Daily data
        - 1mo, 3mo, 6mo: Monthly data
        - 1y, 2y, 5y, 10y: Yearly data
        - ytd: Year to date
        - max: Maximum available data
    """
    try:
        if not ticker or len(ticker.strip()) == 0:
            raise HTTPException(
                status_code=400,
                detail="Ticker symbol is required"
            )
        
        valid_periods = ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"]
        if period not in valid_periods:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid period. Must be one of: {', '.join(valid_periods)}"
            )
        
        data = yfinance_service.get_historical_data(ticker.strip().upper(), period)
        
        # Convert DataFrame to JSON-serializable format
        return {
            "ticker": ticker.upper(),
            "period": period,
            "data": data.to_dict('records') if not data.empty else []
        }
        
    except TickerNotFoundError as e:
        logger.warning(f"Ticker not found: {ticker}")
        raise HTTPException(status_code=404, detail=e.detail)
    except YFinanceError as e:
        logger.error(f"YFinance error for {ticker}: {str(e)}")
        raise HTTPException(status_code=503, detail=e.detail)
    except Exception as e:
        logger.error(f"Unexpected error getting historical data for {ticker}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error") 
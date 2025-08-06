from fastapi import APIRouter, Path, HTTPException, Depends, Query
from typing import Optional, List
import logging

from app.models.schemas import StockInfo, PriceData, CompanyInfo, ErrorResponse, HistoricalDataResponse, HistoricalDataPoint
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
    Get current price data for a stock (single ticker).
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
    "/stock/{tickers}/prices",
    response_model=List[PriceData],
    summary="Get stock price data for multiple tickers",
    description="Get current price information for multiple stocks. Returns a list of price data objects. If a ticker is invalid or fails, it will be omitted from the result.",
    responses={
        200: {"description": "List of price data"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        503: {"model": ErrorResponse, "description": "YFinance service unavailable"}
    }
)
async def get_multiple_stock_prices(
    tickers: str,
    yfinance_service: YFinanceService = Depends(get_yfinance_service),
    current_client: Client = Depends(get_current_client)
) -> list[PriceData]:
    """
    Get current price data for multiple stocks.
    """
    tickers_list = [ticker.strip() for ticker in tickers.split(",") if ticker.strip()]
    logger.info(f"Received request for multiple stock prices: {tickers_list}")
    if not tickers_list:
        logger.warning("No tickers provided or invalid tickers parameter.")
        raise HTTPException(status_code=400, detail="At least one ticker symbol is required")
    results = []
    for ticker in tickers_list:
        try:
            logger.info(f"Fetching price data for ticker: {ticker}")
            price = yfinance_service.get_price_data(ticker.upper())
            logger.info(f"Successfully fetched price data for {ticker}: {price}")
            results.append(price)
        except (TickerNotFoundError, YFinanceError) as e:
            logger.warning(f"Failed to get price for {ticker}: {str(e)}")
            continue
        except Exception as e:
            logger.error(f"Unexpected error getting price data for {ticker}: {str(e)}", exc_info=True)
            continue
    logger.info(f"Returning price data for {len(results)} tickers out of {len(tickers_list)} requested.")
    return results

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
    response_model=HistoricalDataResponse,
    summary="Get historical price data",
    description="Get historical price data for a stock",
    responses={
        200: {"model": HistoricalDataResponse, "description": "Historical data"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        404: {"model": ErrorResponse, "description": "Ticker not found"},
        503: {"model": ErrorResponse, "description": "YFinance service unavailable"}
    }
)
async def get_historical_data(
    ticker: str = Path(..., description="Stock ticker symbol"),
    period: str = Query("1y", description="Time period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)"),
    yfinance_service: YFinanceService = Depends(get_yfinance_service),
    current_client: Client = Depends(get_current_client)
) -> HistoricalDataResponse:
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
        
        ticker_upper = ticker.strip().upper()
        data = yfinance_service.get_historical_data(ticker_upper, period)
        
        # Convert DataFrame to list of HistoricalDataPoint objects
        data_points = []
        if not data.empty:
            for date, row in data.iterrows():
                data_points.append(HistoricalDataPoint(
                    date=date.to_pydatetime(),
                    open=row.get('Open'),
                    high=row.get('High'),
                    low=row.get('Low'),
                    close=row.get('Close'),
                    volume=int(row.get('Volume', 0)),
                    dividends=row.get('Dividends'),
                    stock_splits=row.get('Stock Splits')
                ))
        
        return HistoricalDataResponse(
            symbol=ticker_upper,
            period=period,
            data=data_points
        )
        
    except TickerNotFoundError as e:
        logger.warning(f"Ticker not found: {ticker}")
        raise HTTPException(status_code=404, detail=e.detail)
    except YFinanceError as e:
        logger.error(f"YFinance error for {ticker}: {str(e)}")
        raise HTTPException(status_code=503, detail=e.detail)
    except Exception as e:
        logger.error(f"Unexpected error getting historical data for {ticker}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error") 
from fastapi import APIRouter, Path, HTTPException, Depends, Query, Body
from typing import Optional, List, Dict, Any
import logging
from datetime import datetime, timedelta

from app.models.schemas import (
    StockInfo, PriceData, CompanyInfo, ErrorResponse, HistoricalDataResponse, 
    HistoricalDataPoint, MarketDataResponse, BatchNewsRequest, BatchNewsResponse, 
    TickerNews, NewsArticle
)
from app.services.yfinance_service import YFinanceService, yfinance_service_singleton
from app.core.exceptions import TickerNotFoundError, YFinanceError
from app.core.dependencies import get_current_client

logger = logging.getLogger(__name__)

router = APIRouter()

def get_yfinance_service() -> YFinanceService:
    """Dependency to get the shared yfinance service instance (shared cache)"""
    return yfinance_service_singleton

@router.post(
    "/news/batch",
    response_model=BatchNewsResponse,
    summary="Get news for multiple tickers",
    description="""
    Get news articles for multiple stock tickers in a single request.
    
    - **tickers**: List of stock ticker symbols (max 50)
    - **limit_per_ticker**: Maximum number of news items per ticker (1-20)
    - **days**: Number of days to look back for news (1-30)
    """,
    responses={
        200: {"description": "News articles for the requested tickers"},
        400: {"model": ErrorResponse, "description": "Invalid request parameters"},
        503: {"model": ErrorResponse, "description": "YFinance service unavailable"}
    }
)
def get_batch_news(
    request: BatchNewsRequest,
    yfinance_service: YFinanceService = Depends(get_yfinance_service),
    current_client: Dict[str, Any] = Depends(get_current_client)
) -> BatchNewsResponse:
    """
    Get news articles for multiple stock tickers.
    
    This endpoint allows you to fetch news articles for multiple stocks in a single request.
    Each ticker will return up to the specified number of most recent news articles.
    """
    try:
        # Get news for all tickers
        ticker_news = yfinance_service.get_news_for_tickers(
            tickers=request.tickers,
            limit_per_ticker=request.limit_per_ticker
        )
        
        # Convert to response format
        results = []
        for ticker, articles in ticker_news.items():
            # Convert each article to NewsArticle model
            news_articles = []
            for article in articles:
                try:
                    # Convert published_at to datetime if it's a string
                    published_at = article.get('published_at')
                    if isinstance(published_at, str):
                        try:
                            published_at = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                        except (ValueError, AttributeError):
                            published_at = None
                    
                    news_articles.append(NewsArticle(
                        id=article.get('id'),
                        title=article['title'],
                        publisher=article.get('publisher'),
                        link=article.get('link'),
                        published_at=published_at,
                        thumbnail=article.get('thumbnail'),
                        related_tickers=article.get('related_tickers', []),
                        content_type=article.get('content_type'),
                        summary=article.get('summary'),
                        description=article.get('description'),
                        is_video=article.get('is_video', False)
                    ))
                except Exception as e:
                    logger.error(f"Error formatting article for {ticker}: {str(e)}", exc_info=True)
            
            results.append(TickerNews(
                ticker=ticker,
                news=news_articles
            ))
        
        total_articles = sum(len(tn.news) for tn in results)
        
        return BatchNewsResponse(
            results=results,
            total_articles=total_articles
        )
        
    except Exception as e:
        logger.error(f"Error in get_batch_news: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Failed to fetch news data",
                "detail": str(e)
            }
        )

@router.get(
    "/market",
    response_model=MarketDataResponse,
    summary="Get market overview data",
    description="""
    Get market overview data including:
    - Top gainers
    - Top losers
    - Most active stocks
    
    Data is cached for 5 minutes to reduce API calls.
    """,
    responses={
        200: {"description": "Market overview data"},
        503: {"model": ErrorResponse, "description": "YFinance service unavailable"}
    }
)
def get_market_data(
    yfinance_service: YFinanceService = Depends(get_yfinance_service),
    current_client: Dict[str, Any] = Depends(get_current_client)
) -> MarketDataResponse:
    """
    Get market overview data including top gainers, losers, and most active stocks.
    
    Returns a snapshot of current market activity with key metrics for each stock.
    """
    try:
        return yfinance_service.get_market_data()
    except YFinanceError as e:
        logger.error(f"Error getting market data: {str(e)}")
        raise HTTPException(
            status_code=503,
            detail={"error": "Failed to fetch market data", "detail": str(e)}
        )
    except Exception as e:
        logger.error(f"Unexpected error getting market data: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "detail": str(e)}
        )

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
def get_stock_info(
    ticker: str = Path(..., description="Stock ticker symbol (e.g., AAPL, MSFT)"),
    yfinance_service: YFinanceService = Depends(get_yfinance_service),
    current_client: Dict[str, Any] = Depends(get_current_client)
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
def get_stock_price(
    ticker: str = Path(..., description="Stock ticker symbol"),
    yfinance_service: YFinanceService = Depends(get_yfinance_service),
    current_client: Dict[str, Any] = Depends(get_current_client)
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
def get_multiple_stock_prices(
    tickers: str,
    yfinance_service: YFinanceService = Depends(get_yfinance_service),
    current_client: Dict[str, Any] = Depends(get_current_client)
) -> list[PriceData]:
    """
    Get current price data for multiple stocks.

    Tickers are fetched concurrently via fast_info, so response time stays
    close to a single-ticker request even for large portfolios. Note that
    pe_ratio and dividend_yield are not available on this batch endpoint.
    """
    tickers_list = [ticker.strip() for ticker in tickers.split(",") if ticker.strip()]
    logger.info(f"Received request for multiple stock prices: {tickers_list}")
    if not tickers_list:
        logger.warning("No tickers provided or invalid tickers parameter.")
        raise HTTPException(status_code=400, detail="At least one ticker symbol is required")
    try:
        results = yfinance_service.get_multiple_price_data(tickers_list)
    except Exception as e:
        logger.error(f"Unexpected error getting batch price data: {str(e)}", exc_info=True)
        raise HTTPException(status_code=503, detail={"error": "Failed to fetch price data", "detail": str(e)})
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
def get_company_info(
    ticker: str = Path(..., description="Stock ticker symbol"),
    yfinance_service: YFinanceService = Depends(get_yfinance_service),
    current_client: Dict[str, Any] = Depends(get_current_client)
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
def get_historical_data(
    ticker: str = Path(..., description="Stock ticker symbol"),
    period: str = Query("1y", description="Time period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)"),
    yfinance_service: YFinanceService = Depends(get_yfinance_service),
    current_client: Dict[str, Any] = Depends(get_current_client)
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
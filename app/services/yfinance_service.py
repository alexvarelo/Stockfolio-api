import yfinance as yf
from typing import Optional, Dict, Any, List
import pandas as pd
from datetime import datetime
import logging
import time

from app.core.exceptions import TickerNotFoundError, YFinanceError
from app.models.schemas import PriceData, CompanyInfo, StockInfo

logger = logging.getLogger(__name__)

class YFinanceService:
    """Service class for handling yfinance operations"""
    
    def __init__(self):
        self.cache = {}
        self.last_request_time = 0
        self.min_request_interval = 3.0  # Increased to 3 seconds between requests
        self.cache_duration = 300  # Cache for 5 minutes

    def _rate_limit(self):
        """Implement rate limiting to avoid Yahoo Finance restrictions"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def get_ticker(self, symbol: str) -> yf.Ticker:
        """Get yfinance Ticker object for a given symbol with retry logic and caching"""
        symbol_upper = symbol.upper()
        
        # Check cache first
        cache_key = f"ticker_{symbol_upper}"
        current_time = time.time()
        
        if cache_key in self.cache:
            cached_data = self.cache[cache_key]
            if current_time - cached_data['timestamp'] < self.cache_duration:
                logger.debug(f"Using cached data for {symbol_upper}")
                return cached_data['ticker']
        
        max_retries = 3
        retry_delay = 5.0
        
        for attempt in range(max_retries):
            try:
                self._rate_limit() # Apply rate limiting
                ticker = yf.Ticker(symbol_upper)
                # Test if ticker exists by trying to get basic info
                info = ticker.info
                if not info or 'regularMarketPrice' not in info:
                    raise TickerNotFoundError(symbol)
                
                # Cache the successful result
                self.cache[cache_key] = {
                    'ticker': ticker,
                    'timestamp': current_time
                }
                
                return ticker
            except Exception as e:
                error_str = str(e)
                logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for {symbol}: {error_str}")
                
                if "No data found" in error_str or "symbol may be delisted" in error_str:
                    raise TickerNotFoundError(symbol)
                
                # Handle rate limiting specifically
                if "429" in error_str or "Too Many Requests" in error_str:
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                        logger.info(f"Rate limited for {symbol}, waiting {wait_time} seconds before retry")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise YFinanceError("get_ticker", "Rate limit exceeded after multiple retries. Please try again later.")
                
                # For other errors, raise immediately
                raise YFinanceError("get_ticker", error_str)
        
        raise YFinanceError("get_ticker", "Max retries exceeded")
    
    def get_stock_info(self, symbol: str) -> StockInfo:
        """Get comprehensive stock information"""
        try:
            ticker = self.get_ticker(symbol)
            info = ticker.info
            
            # Extract price data
            price_data = PriceData(
                symbol=symbol.upper(),
                current_price=info.get('regularMarketPrice'),
                previous_close=info.get('previousClose'),
                open=info.get('open'),
                high=info.get('dayHigh'),
                low=info.get('dayLow'),
                volume=info.get('volume'),
                market_cap=info.get('marketCap'),
                pe_ratio=info.get('trailingPE'),
                dividend_yield=info.get('dividendYield'),
                change=info.get('regularMarketPrice', 0) - info.get('previousClose', 0) if info.get('regularMarketPrice') and info.get('previousClose') else None,
                change_percent=info.get('regularMarketChangePercent'),
                last_updated=datetime.now()
            )
            
            # Extract company info
            company_info = CompanyInfo(
                symbol=symbol.upper(),
                name=info.get('longName', info.get('shortName', 'Unknown')),
                sector=info.get('sector'),
                industry=info.get('industry'),
                country=info.get('country'),
                website=info.get('website'),
                description=info.get('longBusinessSummary'),
                employees=info.get('fullTimeEmployees'),
                founded=info.get('founded')
            )
            
            return StockInfo(
                symbol=symbol.upper(),
                price_data=price_data,
                company_info=company_info,
                additional_data=info
            )
            
        except (TickerNotFoundError, YFinanceError):
            raise
        except Exception as e:
            logger.error(f"Error getting stock info for {symbol}: {str(e)}")
            raise YFinanceError("get_stock_info", str(e))
    
    def get_price_data(self, symbol: str) -> PriceData:
        """Get current price data for a stock"""
        try:
            ticker = self.get_ticker(symbol)
            info = ticker.info
            
            return PriceData(
                symbol=symbol.upper(),
                current_price=info.get('regularMarketPrice'),
                previous_close=info.get('previousClose'),
                open=info.get('open'),
                high=info.get('dayHigh'),
                low=info.get('dayLow'),
                volume=info.get('volume'),
                market_cap=info.get('marketCap'),
                pe_ratio=info.get('trailingPE'),
                dividend_yield=info.get('dividendYield'),
                change=info.get('regularMarketPrice', 0) - info.get('previousClose', 0) if info.get('regularMarketPrice') and info.get('previousClose') else None,
                change_percent=info.get('regularMarketChangePercent'),
                last_updated=datetime.now()
            )
            
        except (TickerNotFoundError, YFinanceError):
            raise
        except Exception as e:
            logger.error(f"Error getting price data for {symbol}: {str(e)}")
            raise YFinanceError("get_price_data", str(e))
    
    def get_company_info(self, symbol: str) -> CompanyInfo:
        """Get company information for a stock"""
        try:
            ticker = self.get_ticker(symbol)
            info = ticker.info
            
            return CompanyInfo(
                symbol=symbol.upper(),
                name=info.get('longName', info.get('shortName', 'Unknown')),
                sector=info.get('sector'),
                industry=info.get('industry'),
                country=info.get('country'),
                website=info.get('website'),
                description=info.get('longBusinessSummary'),
                employees=info.get('fullTimeEmployees'),
                founded=info.get('founded')
            )
            
        except (TickerNotFoundError, YFinanceError):
            raise
        except Exception as e:
            logger.error(f"Error getting company info for {symbol}: {str(e)}")
            raise YFinanceError("get_company_info", str(e))
    
    def get_historical_data(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        """Get historical price data"""
        try:
            ticker = self.get_ticker(symbol)
            return ticker.history(period=period)
        except (TickerNotFoundError, YFinanceError):
            raise
        except Exception as e:
            logger.error(f"Error getting historical data for {symbol}: {str(e)}")
            raise YFinanceError("get_historical_data", str(e)) 
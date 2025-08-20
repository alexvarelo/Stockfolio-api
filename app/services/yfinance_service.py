import yfinance as yf
from typing import Optional, Dict, Any, List
import pandas as pd
from datetime import datetime
import logging
import time

from app.core.exceptions import TickerNotFoundError, YFinanceError
from app.models.schemas import PriceData, CompanyInfo, StockInfo, HistoricalDataResponse, HistoricalDataPoint, MarketData, MarketDataResponse

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
    
    def _get_news_articles(self, ticker: yf.Ticker) -> List[Dict[str, Any]]:
        """Get news articles for a given ticker"""
        try:
            logger.debug(f"Attempting to fetch news for ticker: {ticker.ticker}")
            
            # Try to get news using the news attribute
            if hasattr(ticker, 'news') and callable(ticker.news):
                logger.debug("Using ticker.news() method to fetch news")
                news = ticker.news
                logger.info(f"Retrieved {len(news)} news articles using ticker.news() {news}")
                return news
            
            # Fallback to alternative method if available
            if hasattr(ticker, 'get_news') and callable(ticker.get_news):
                logger.debug("Using ticker.get_news() method to fetch news")
                news = ticker.get_news()
                logger.info(f"Retrieved {len(news)} news articles using ticker.get_news() {news}")
                return news
                
            logger.warning("No news methods available on ticker object")
            return []
            
        except Exception as e:
            logger.error(f"Error fetching news data for {ticker.ticker}: {str(e)}", exc_info=True)
            return []
    
    def get_news_for_tickers(self, tickers: List[str], limit_per_ticker: int = 5) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get news articles for multiple tickers
        
        Args:
            tickers: List of stock ticker symbols
            limit_per_ticker: Maximum number of news items per ticker
            
        Returns:
            Dictionary mapping tickers to their news articles
        """
        logger.info(f"Fetching news for {len(tickers)} tickers")
        all_news = {}
        
        for ticker_symbol in tickers:
            try:
                ticker = self.get_ticker(ticker_symbol)
                news_data = self._get_news_articles(ticker)[:limit_per_ticker]
                
                processed_articles = []
                for article in news_data:
                    try:
                        content = article.get('content', article)
                        
                        # Extract thumbnail
                        thumbnail = {}
                        if 'thumbnail' in content:
                            thumb_data = content['thumbnail']
                            if 'resolutions' in thumb_data and thumb_data['resolutions']:
                                thumbnail['url'] = thumb_data['resolutions'][0].get('url')
                            elif 'originalUrl' in thumb_data:
                                thumbnail['url'] = thumb_data['originalUrl']
                            
                            if 'originalWidth' in thumb_data:
                                thumbnail['width'] = thumb_data['originalWidth']
                            if 'originalHeight' in thumb_data:
                                thumbnail['height'] = thumb_data['originalHeight']
                            if 'caption' in thumb_data:
                                thumbnail['caption'] = thumb_data['caption']
                        
                        article_data = {
                            'id': content.get('id'),
                            'title': content.get('title', ''),
                            'content_type': content.get('contentType', 'ARTICLE'),
                            'summary': content.get('summary', ''),
                            'published_at': content.get('pubDate'),
                            'publisher': content.get('provider', {}).get('displayName', ''),
                            'link': content.get('clickThroughUrl', {}).get('url', ''),
                            'thumbnail': thumbnail or None,
                            'is_video': content.get('contentType') == 'VIDEO',
                            'description': content.get('description', ''),
                            'related_tickers': content.get('relatedTickers', [])
                        }
                        processed_articles.append(article_data)
                        
                    except Exception as e:
                        logger.error(f"Error processing article for {ticker_symbol}: {str(e)}", exc_info=True)
                
                all_news[ticker_symbol] = processed_articles
                
            except Exception as e:
                logger.error(f"Error fetching news for {ticker_symbol}: {str(e)}")
                all_news[ticker_symbol] = []
        
        return all_news
        
    def get_stock_info(self, symbol: str) -> StockInfo:
        """Get comprehensive stock information including news"""
        try:
            ticker = self.get_ticker(symbol)
            info = ticker.info
            
            # Get news articles
            news_data = self._get_news_articles(ticker)
            news_articles = []
            
            for article in news_data:
                try:
                    # Handle both direct article format and nested content format
                    content = article.get('content', article)
                    
                    # Extract thumbnail - ensure it's always a dictionary with a URL field
                    thumbnail = {}
                    if 'thumbnail' in content:
                        thumb_data = content['thumbnail']
                        if 'resolutions' in thumb_data and thumb_data['resolutions']:
                            thumbnail['url'] = thumb_data['resolutions'][0].get('url')
                        elif 'originalUrl' in thumb_data:
                            thumbnail['url'] = thumb_data['originalUrl']
                        
                        # Preserve other thumbnail properties if they exist
                        if 'originalWidth' in thumb_data:
                            thumbnail['width'] = thumb_data['originalWidth']
                        if 'originalHeight' in thumb_data:
                            thumbnail['height'] = thumb_data['originalHeight']
                        if 'caption' in thumb_data:
                            thumbnail['caption'] = thumb_data['caption']
                    
                    # Handle different content types
                    article_data = {
                        'id': content.get('id'),
                        'title': content.get('title', ''),
                        'content_type': content.get('contentType', 'ARTICLE'),
                        'summary': content.get('summary', ''),
                        'published_at': content.get('pubDate'),
                        'publisher': content.get('provider', {}).get('displayName', ''),
                        'link': content.get('clickThroughUrl', {}).get('url', ''),
                        'thumbnail': thumbnail,
                        'is_video': content.get('contentType') == 'VIDEO',
                        'description': content.get('description', '')
                    }
                    
                    # Add related tickers if available
                    if 'relatedTickers' in content:
                        article_data['related_tickers'] = content['relatedTickers']
                    
                    news_articles.append(article_data)
                    
                except Exception as e:
                    logger.warning(f"Error processing news article: {str(e)}", exc_info=True)
            
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
            
            # Create StockInfo with news articles
            return StockInfo(
                symbol=symbol.upper(),
                price_data=price_data,
                company_info=company_info,
                news=news_articles,
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
            
    def get_market_data(self) -> MarketDataResponse:
        """Get market data including top gainers, losers, and most active stocks"""
        cache_key = "market_data"
        current_time = time.time()
        
        # Check cache first
        if cache_key in self.cache:
            cached_data = self.cache[cache_key]
            if current_time - cached_data['timestamp'] < self.cache_duration:
                logger.debug("Using cached market data")
                return cached_data['data']
        
        try:
            self._rate_limit()
            
            # Initialize Market with 'us_market' parameter
            market = yf.Market('us_market')
            
            # Get top gainers
            gainers = market.get_top_gainers()
            gainers_data = [
                MarketData(
                    symbol=row['symbol'],
                    name=row.get('shortName', ''),
                    price=row.get('regularMarketPrice'),
                    change=row.get('regularMarketChange'),
                    change_percent=row.get('regularMarketChangePercent'),
                    volume=row.get('regularMarketVolume'),
                    market_cap=row.get('marketCap'),
                    pe_ratio=row.get('trailingPE')
                ) for _, row in gainers.iterrows()
            ]
            
            # Get top losers
            losers = market.get_top_losers()
            losers_data = [
                MarketData(
                    symbol=row['symbol'],
                    name=row.get('shortName', ''),
                    price=row.get('regularMarketPrice'),
                    change=row.get('regularMarketChange'),
                    change_percent=row.get('regularMarketChangePercent'),
                    volume=row.get('regularMarketVolume'),
                    market_cap=row.get('marketCap'),
                    pe_ratio=row.get('trailingPE')
                ) for _, row in losers.iterrows()
            ]
            
            # Get most active stocks
            active = market.get_most_active()
            active_data = [
                MarketData(
                    symbol=row['symbol'],
                    name=row.get('shortName', ''),
                    price=row.get('regularMarketPrice'),
                    change=row.get('regularMarketChange'),
                    change_percent=row.get('regularMarketChangePercent'),
                    volume=row.get('regularMarketVolume'),
                    market_cap=row.get('marketCap'),
                    pe_ratio=row.get('trailingPE')
                ) for _, row in active.iterrows()
            ]
            
            response = MarketDataResponse(
                gainers=gainers_data,
                losers=losers_data,
                active=active_data,
                last_updated=datetime.now()
            )
            
            # Cache the result
            self.cache[cache_key] = {
                'data': response,
                'timestamp': current_time
            }
            
            return response
            
        except Exception as e:
            logger.error(f"Error getting market data: {str(e)}")
            raise YFinanceError("get_market_data", str(e))
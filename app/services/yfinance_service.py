import yfinance as yf
from typing import Optional, Dict, Any, List
import pandas as pd
from datetime import datetime
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.core.exceptions import TickerNotFoundError, YFinanceError
from app.models.schemas import PriceData, CompanyInfo, StockInfo, HistoricalDataResponse, HistoricalDataPoint, MarketData, MarketDataResponse

logger = logging.getLogger(__name__)

class YFinanceService:
    """Service class for handling yfinance operations"""

    def __init__(self):
        self.cache = {}
        self._cache_lock = threading.Lock()
        self.last_request_time = 0
        self.min_request_interval = 3.0  # Increased to 3 seconds between requests
        self.cache_duration = 300  # Cache for 5 minutes
        self.price_cache_duration = 30  # Prices go stale quickly; cache for 30 seconds
        self.max_price_workers = 8

    def _cache_get(self, key: str, max_age: float) -> Optional[Any]:
        """Return a cached value if it is younger than max_age seconds"""
        with self._cache_lock:
            entry = self.cache.get(key)
            if entry and time.time() - entry['timestamp'] < max_age:
                return entry['value']
        return None

    def _cache_set(self, key: str, value: Any) -> None:
        with self._cache_lock:
            self.cache[key] = {'value': value, 'timestamp': time.time()}

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

        cached = self._cache_get(cache_key, self.cache_duration)
        if cached is not None:
            logger.debug(f"Using cached data for {symbol_upper}")
            return cached
        
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
                self._cache_set(cache_key, ticker)

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
    
    def get_price_data_fast(self, symbol: str) -> PriceData:
        """
        Get current price data using yfinance fast_info.

        Much faster than get_price_data because it avoids the full quoteSummary
        scrape behind Ticker.info, and skips the global request throttle.
        Trade-off: pe_ratio and dividend_yield are not available via fast_info.
        Results are cached for price_cache_duration seconds.
        """
        symbol_upper = symbol.upper()
        cache_key = f"price_{symbol_upper}"

        cached = self._cache_get(cache_key, self.price_cache_duration)
        if cached is not None:
            return cached

        try:
            fast_info = yf.Ticker(symbol_upper).fast_info
            current_price = fast_info.last_price
            if current_price is None:
                raise TickerNotFoundError(symbol_upper)

            previous_close = fast_info.previous_close
            change = None
            change_percent = None
            if current_price is not None and previous_close:
                change = current_price - previous_close
                change_percent = (change / previous_close) * 100

            last_volume = fast_info.last_volume
            price_data = PriceData(
                symbol=symbol_upper,
                current_price=current_price,
                previous_close=previous_close,
                open=fast_info.open,
                high=fast_info.day_high,
                low=fast_info.day_low,
                volume=int(last_volume) if last_volume else None,
                market_cap=fast_info.market_cap,
                pe_ratio=None,
                dividend_yield=None,
                change=change,
                change_percent=change_percent,
                last_updated=datetime.now()
            )

            self._cache_set(cache_key, price_data)
            return price_data

        except TickerNotFoundError:
            raise
        except (KeyError, AttributeError):
            raise TickerNotFoundError(symbol_upper)
        except Exception as e:
            logger.error(f"Error getting fast price data for {symbol}: {str(e)}")
            raise YFinanceError("get_price_data_fast", str(e))

    def get_multiple_price_data(self, symbols: List[str]) -> List[PriceData]:
        """
        Get current price data for multiple tickers concurrently.

        Fetches all tickers in parallel using fast_info, so a 20-holding
        portfolio takes roughly the time of a single request instead of
        20 sequential throttled requests. Failed tickers are omitted.
        """
        unique_symbols = list(dict.fromkeys(s.upper() for s in symbols))
        results: Dict[str, PriceData] = {}

        with ThreadPoolExecutor(max_workers=min(self.max_price_workers, len(unique_symbols))) as executor:
            futures = {
                executor.submit(self.get_price_data_fast, symbol): symbol
                for symbol in unique_symbols
            }
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    results[symbol] = future.result()
                except (TickerNotFoundError, YFinanceError) as e:
                    logger.warning(f"Skipping {symbol} in batch price request: {str(e)}")
                except Exception as e:
                    logger.error(f"Unexpected error fetching {symbol} in batch: {str(e)}")

        # Preserve the order the symbols were requested in
        return [results[s] for s in unique_symbols if s in results]

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
            
    def _screen_market_movers(self, screener_key: str, count: int = 25) -> List[MarketData]:
        """Run a predefined yfinance screener and map the quotes to MarketData"""
        response = yf.screen(screener_key, count=count)
        quotes = response.get('quotes', []) if isinstance(response, dict) else []

        movers = []
        for quote in quotes:
            symbol = quote.get('symbol')
            if not symbol:
                continue
            movers.append(MarketData(
                symbol=symbol,
                name=quote.get('shortName') or quote.get('longName') or '',
                price=quote.get('regularMarketPrice'),
                change=quote.get('regularMarketChange'),
                change_percent=quote.get('regularMarketChangePercent'),
                volume=quote.get('regularMarketVolume'),
                market_cap=quote.get('marketCap'),
                pe_ratio=quote.get('trailingPE')
            ))
        return movers

    def get_market_data(self) -> MarketDataResponse:
        """Get market data including top gainers, losers, and most active stocks"""
        cache_key = "market_data"

        cached = self._cache_get(cache_key, self.cache_duration)
        if cached is not None:
            logger.debug("Using cached market data")
            return cached

        try:
            self._rate_limit()

            # yf.Market no longer exposes get_top_gainers/losers/most_active;
            # the predefined screeners are the supported replacement.
            response = MarketDataResponse(
                gainers=self._screen_market_movers('day_gainers'),
                losers=self._screen_market_movers('day_losers'),
                active=self._screen_market_movers('most_actives'),
                last_updated=datetime.now()
            )

            self._cache_set(cache_key, response)
            return response

        except Exception as e:
            logger.error(f"Error getting market data: {str(e)}")
            raise YFinanceError("get_market_data", str(e))


# Module-level singleton. The service was previously instantiated per request,
# which made the cache useless and re-applied the rate-limit delay on every call.
yfinance_service_singleton = YFinanceService()
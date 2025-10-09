import yfinance as yf
from typing import List, Optional, Dict, Any, Union
import logging
import re
import pandas as pd

from app.models.schemas import SearchResult, EquityQuery
from app.core.exceptions import SearchError

logger = logging.getLogger(__name__)

class SearchService:
    """Service class for handling search operations"""
    
    def __init__(self):
        self.cache = {}
    
    def search_instruments(self, query: str, limit: int = 20) -> List[SearchResult]:
        """
        Search for financial instruments by name, ISIN, or ticker symbol
        
        Args:
            query: Search query string
            limit: Maximum number of results to return
            
        Returns:
            List of SearchResult objects
        """
        try:
            # Clean and validate query
            query = query.strip().upper()
            if not query or len(query) < 2:
                return []
            
            results = []
            
            # Try direct ticker lookup first
            direct_result = self._try_direct_ticker(query)
            if direct_result:
                results.append(direct_result)
            
            # Only do additional search if we have room for more results
            if len(results) < limit:
                # Search using yfinance search functionality
                search_results = self._search_yfinance(query)
                results.extend(search_results)
                
                # If we still don't have results, try the direct ticker approach
                if not results and len(query) >= 2:
                    # Try some common variations
                    variations = self._get_search_variations(query)
                    for variation in variations[:3]:  # Limit to first 3 variations
                        try:
                            result = self._try_direct_ticker(variation)
                            if result:
                                results.append(result)
                                break
                        except Exception:
                            continue
            
            # Remove duplicates and limit results
            unique_results = self._deduplicate_results(results)
            return unique_results[:limit]
            
        except Exception as e:
            logger.error(f"Search error for query '{query}': {str(e)}")
            raise SearchError(query, str(e))
    
    def _try_direct_ticker(self, query: str) -> Optional[SearchResult]:
        """Try to get information for a direct ticker symbol"""
        try:
            ticker = yf.Ticker(query)
            info = ticker.info
            
            if info and 'regularMarketPrice' in info:
                return SearchResult(
                    symbol=query,
                    name=info.get('longName', info.get('shortName', query)),
                    exchange=info.get('exchange'),
                    type=self._determine_instrument_type(info),
                    isin=info.get('isin'),
                    country=info.get('country')
                )
        except Exception:
            pass
        return None
    
    def _search_yfinance(self, query: str) -> List[SearchResult]:
        """Search using yfinance search functionality"""
        try:
            # Add rate limiting
            import time
            time.sleep(3)  # Increased delay to avoid rate limiting
            
            # Use the proper yfinance Search class
            search = yf.Search(query, max_results=5)  # Reduced max results
            search_results = search.search()
            
            results = []
            for quote in search_results.quotes:
                try:
                    # Add basic result without additional API calls to avoid rate limiting
                    results.append(SearchResult(
                        symbol=quote['symbol'],
                        name=quote.get('longname', quote.get('shortname', quote['symbol'])),
                        exchange=quote.get('exchDisp'),
                        type=self._determine_instrument_type_from_quote(quote),
                        isin=None,
                        country=None
                    ))
                except Exception as e:
                    logger.debug(f"Failed to process quote {quote.get('symbol', 'unknown')}: {str(e)}")
                    continue
                    
            return results
            
        except Exception as e:
            logger.warning(f"YFinance search failed for '{query}': {str(e)}")
            return []
    
    def _determine_instrument_type_from_quote(self, quote: dict) -> str:
        """Determine instrument type from search quote data"""
        quote_type = quote.get('quoteType', '').lower()
        
        if quote_type == 'equity':
            return 'Stock'
        elif quote_type == 'etf':
            return 'ETF'
        elif quote_type == 'mutualfund':
            return 'Mutual Fund'
        elif quote_type == 'index':
            return 'Index'
        elif quote_type == 'currency':
            return 'Currency'
        elif quote_type == 'cryptocurrency':
            return 'Cryptocurrency'
        else:
            return 'Unknown'
    
    def _determine_instrument_type(self, info: dict) -> str:
        """Determine the type of financial instrument"""
        quote_type = info.get('quoteType', '').lower()
        
        if quote_type == 'equity':
            return 'Stock'
        elif quote_type == 'etf':
            return 'ETF'
        elif quote_type == 'mutualfund':
            return 'Mutual Fund'
        elif quote_type == 'index':
            return 'Index'
        elif quote_type == 'currency':
            return 'Currency'
        elif quote_type == 'cryptocurrency':
            return 'Cryptocurrency'
        else:
            return 'Unknown'
    
    def _deduplicate_results(self, results: List[SearchResult]) -> List[SearchResult]:
        """Remove duplicate results based on symbol"""
        seen_symbols = set()
        unique_results = []
        
        for result in results:
            if result.symbol not in seen_symbols:
                seen_symbols.add(result.symbol)
                unique_results.append(result)
                
        return unique_results
        
    def _get_search_variations(self, query: str) -> List[str]:
        """Generate common search variations for a query"""
        variations = [query]
        
        # Add variations with common suffixes
        common_suffixes = ['', ' INC', ' CORP', ' LTD', ' GROUP', ' HOLDINGS', 
                         ' TECHNOLOGIES', ' INTERNATIONAL', ' CO', ' COMPANY']
        
        for suffix in common_suffixes:
            if not query.endswith(suffix):
                variations.append(f"{query}{suffix}")
                
        # Try with/without spaces and dots
        variations.append(query.replace(' ', ''))
        variations.append(query.replace('.', ''))
        variations.append(query.replace(' ', '').replace('.', ''))
        
        # Remove duplicates while preserving order
        seen = set()
        return [x for x in variations if not (x in seen or seen.add(x))]
    
    def search_by_isin(self, isin: str) -> Optional[SearchResult]:
        """Search for a specific instrument by ISIN"""
        try:
            # ISIN search is limited in yfinance, but we can try
            # This is a simplified implementation
            query = isin.strip().upper()
            
            # Try direct search
            results = self.search_instruments(query, limit=10)
            
            # Look for exact ISIN match
            for result in results:
                if result.isin and result.isin.upper() == isin.upper():
                    return result
            
            return None
            
        except Exception as e:
            logger.error(f"ISIN search error for '{isin}': {str(e)}")
            raise SearchError(isin, str(e))
    
    def get_popular_stocks(self) -> List[SearchResult]:
        """Get a list of popular stocks"""
        popular_symbols = [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'NFLX',
            'SPY', 'QQQ', 'VTI', 'VOO', 'BRK-B', 'JPM', 'JNJ', 'PG', 'UNH'
        ]
        
        results = []
        for symbol in popular_symbols:
            try:
                result = self._try_direct_ticker(symbol)
                if result:
                    results.append(result)
            except Exception:
                continue
        
        return results
    
    def _evaluate_condition(self, stock_data: Dict[str, Any], condition: Dict) -> bool:
        """Evaluate a single condition against stock data"""
        operator = condition['operator'].lower()
        field = condition.get('field')
        value = condition.get('value')
        
        if operator in ['and', 'or']:
            if not condition.get('conditions'):
                return operator == 'and'  # Empty AND is True, empty OR is False
                
            results = [self._evaluate_condition(stock_data, c) for c in condition['conditions']]
            if operator == 'and':
                return all(results)
            return any(results)
            
        if field not in stock_data:
            return False
            
        stock_value = stock_data[field]
        
        # Handle None values
        if stock_value is None:
            return False
        
        if operator == 'eq':
            return stock_value == value
        elif operator == 'ne':
            return stock_value != value
        elif operator == 'gt':
            return stock_value > value
        elif operator == 'lt':
            return stock_value < value
        elif operator == 'gte':
            return stock_value >= value
        elif operator == 'lte':
            return stock_value <= value
        elif operator == 'contains':
            return value.lower() in str(stock_value).lower()
        elif operator == 'is-in':
            return stock_value in value if isinstance(value, (list, tuple, set)) else stock_value == value
        elif operator == 'starts-with':
            return str(stock_value).lower().startswith(str(value).lower())
        elif operator == 'ends-with':
            return str(stock_value).lower().endswith(str(value).lower())
            
        return False
    
    def _get_stock_data(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Get comprehensive stock data for a ticker"""
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # Skip if no data
            if not info or not info.get('symbol'):
                return None
                
            # Extract relevant fields
            data = {
                'symbol': ticker,
                'name': info.get('shortName') or info.get('longName', ''),
                'exchange': info.get('exchange'),
                'sector': info.get('sector'),
                'industry': info.get('industry'),
                'country': info.get('country'),
                'marketCap': info.get('marketCap'),
                'price': info.get('currentPrice') or info.get('regularMarketPrice'),
                'volume': info.get('volume'),
                'epsgrowth.lasttwelvemonths': info.get('earningsGrowth'),
                'quoteType': info.get('quoteType'),
            }
            
            # Add all info fields for flexible querying
            for key, value in info.items():
                if isinstance(value, (str, int, float, bool)) and value is not None:
                    data[key] = value
            
            return data
            
        except Exception as e:
            logger.warning(f"Error fetching data for {ticker}: {str(e)}")
            return None
    
    def _convert_to_yfinance_query(self, query_dict: Dict[str, Any]):
        """
        Convert our query dict to yfinance EquityQuery format
        
        Args:
            query_dict: Our API query format
            
        Returns:
            yfinance.EquityQuery object
        """
        from yfinance import EquityQuery as YFEquityQuery
        
        operator = query_dict.get('operator')
        field = query_dict.get('field')
        value = query_dict.get('value')
        conditions = query_dict.get('conditions')
        
        # Handle logical operators (and, or)
        if operator in ['and', 'or'] and conditions:
            # Recursively convert nested conditions
            converted_conditions = [self._convert_to_yfinance_query(cond) for cond in conditions]
            return YFEquityQuery(operator, converted_conditions)
        
        # Handle comparison operators (eq, lt, gt, etc.)
        # For yfinance, the format is: EquityQuery('operator', ['field', value])
        # or for 'is-in': EquityQuery('is-in', ['field', value1, value2, ...])
        if operator == 'is-in':
            # Format: EquityQuery('is-in', ['exchange', 'NMS', 'NYQ'])
            return YFEquityQuery(operator, [field] + (value if isinstance(value, list) else [value]))
        else:
            # Format: EquityQuery('lt', ['epsgrowth.lasttwelvemonths', 15])
            return YFEquityQuery(operator, [field, value])
    
    def screen_equities(self, query: Union[Dict, EquityQuery, str, None] = None, page: int = 1, page_size: int = 20, predefined_screener: Optional[str] = None) -> Dict[str, Any]:
        """
        Screen equities based on complex query conditions or predefined screeners with pagination
        
        Args:
            query: EquityQuery object, dict with screening criteria, or None if using predefined screener
            page: Page number (1-indexed)
            page_size: Number of results per page
            predefined_screener: Name of predefined screener (e.g., 'day_gainers', 'most_actives')
            
        Returns:
            Dictionary with pagination metadata and list of matching instruments
        """
        all_results = []
        query_dict = None
        screener_name = None
        # Compute offset from page and page_size for yfinance pagination
        offset = max((page - 1) * page_size, 0)
        
        try:
            # Determine if using predefined screener or custom query
            if predefined_screener:
                # Use predefined screener with pagination
                logger.info(f"Executing yfinance screen with predefined screener: {predefined_screener}, offset={offset}, size={page_size}")
                screen_result = yf.screen(predefined_screener, offset=offset, size=page_size)
                screener_name = predefined_screener
            else:
                # Use custom query
                # Convert query to dict if it's an EquityQuery object
                if isinstance(query, EquityQuery):
                    query_dict = query.dict()
                elif isinstance(query, dict):
                    query_dict = query
                else:
                    raise ValueError("Either 'query' or 'predefined_screener' must be provided")
                
                # Convert our query format to yfinance EquityQuery format
                yf_query = self._convert_to_yfinance_query(query_dict)
                
                logger.info(f"Executing yfinance screen with custom query: {yf_query}, offset={offset}, size={page_size}")
                
                # Use yfinance screen function with pagination
                screen_result = yf.screen(yf_query, offset=offset, size=page_size)
            
            # Process the screening results
            if screen_result is not None:
                # yf.screen() returns a dict with 'quotes', 'total', 'count', 'start' keys
                if isinstance(screen_result, dict) and 'quotes' in screen_result:
                    # Extract quotes and pagination metadata from the response
                    quotes = screen_result.get('quotes', [])
                    total_results = screen_result.get('total', 0)
                    count_returned = screen_result.get('count', len(quotes))
                    start_offset = screen_result.get('start', offset)
                    
                    logger.info(f"Found {count_returned} quotes out of {total_results} total results")
                    
                    for quote in quotes:
                        try:
                            all_results.append(SearchResult(
                                symbol=quote.get('symbol'),
                                name=quote.get('shortName') or quote.get('longName', ''),
                                exchange=quote.get('exchange'),
                                type=quote.get('quoteType') or 'EQUITY',
                                currency=quote.get('currency'),
                                country=None,  # Not always available in quotes
                                
                                # Price fields
                                regular_market_price=quote.get('regularMarketPrice'),
                                regular_market_change=quote.get('regularMarketChange'),
                                regular_market_change_percent=quote.get('regularMarketChangePercent'),
                                intraday_price_change=quote.get('regularMarketChange'),  # Same as regularMarketChange
                                bid=quote.get('bid'),
                                ask=quote.get('ask'),
                                fifty_two_week_high=quote.get('fiftyTwoWeekHigh'),
                                fifty_two_week_low=quote.get('fiftyTwoWeekLow'),
                                fifty_two_week_change_percent=quote.get('fiftyTwoWeekChangePercent'),
                                
                                # Fundamental fields
                                sector=quote.get('sector'),
                                industry=quote.get('industry'),
                                market_cap=quote.get('marketCap'),
                                pe_ratio=quote.get('trailingPE'),
                                forward_pe=quote.get('forwardPE'),
                                price_to_book=quote.get('priceToBook'),
                                
                                # Growth and earnings
                                eps_trailing_twelve_months=quote.get('epsTrailingTwelveMonths'),
                                eps_forward=quote.get('epsForward'),
                                eps_current_year=quote.get('epsCurrentYear'),
                                earnings_growth=quote.get('earningsGrowth'),
                                
                                # Analyst ratings
                                average_analyst_rating=quote.get('averageAnalystRating'),
                                
                                # Volume and trading
                                regular_market_volume=quote.get('regularMarketVolume'),
                                average_daily_volume_3_month=quote.get('averageDailyVolume3Month')
                            ))
                        except Exception as e:
                            logger.warning(f"Error processing quote {quote.get('symbol', 'unknown')}: {str(e)}")
                            continue
                    
                    # Calculate pagination using yfinance's metadata
                    total_pages = (total_results + page_size - 1) // page_size if total_results > 0 else 1
                    has_next = (start_offset + count_returned) < total_results if total_results is not None else False
                    
                    return {
                        'total': total_results,
                        'count': len(all_results),
                        'start': start_offset,
                        'returned': count_returned,
                        'page': page,
                        'page_size': page_size,
                        'total_pages': total_pages,
                        'has_next': has_next,
                        'results': all_results,
                        'query': query_dict,
                        'screener': screener_name
                    }
                else:
                    logger.warning(f"Unexpected screen_result format: {type(screen_result)}")
                    
            # Fallback if no results
            return {
                'total': 0,
                'count': 0,
                'start': offset,
                'returned': 0,
                'page': page,
                'page_size': page_size,
                'total_pages': 1,
                'has_next': False,
                'results': [],
                'query': query_dict,
                'screener': screener_name
            }
            
        except Exception as e:
            logger.error(f"Error in screen_equities: {str(e)}", exc_info=True)
            raise SearchError("equity_screen", f"Failed to screen equities: {str(e)}") 
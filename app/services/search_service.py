import yfinance as yf
from typing import List, Optional
import logging
import re

from app.models.schemas import SearchResult
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
        """Generate common variations of a search query"""
        variations = []
        
        # Original query
        variations.append(query)
        
        # Common suffixes to try appending/removing
        suffixes = ['.TO', '.V', '.NE', '.BE', '.F', '.DE', '.PA', '.L', '.MI', '.AS', '.BR', '.AX', 
                   '.NZ', '.SI', '.KS', '.KQ', '.SS', '.SZ', '.HK', '.T', '.TWO', '.TW', '.SR']
        
        # Try removing any existing suffix and adding common ones
        base_query = query
        for suffix in suffixes:
            if query.endswith(suffix):
                base_query = query[:-len(suffix)]
                variations.append(base_query)
                break
        
        # Add common suffixes
        for suffix in suffixes:
            variations.append(f"{base_query}{suffix}")
        
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
from fastapi import HTTPException, status
from typing import Any, Dict, Optional

class FinancialDataException(HTTPException):
    """Base exception for financial data errors"""
    def __init__(
        self,
        status_code: int,
        detail: str,
        headers: Optional[Dict[str, Any]] = None
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)

class TickerNotFoundError(FinancialDataException):
    """Raised when a ticker symbol is not found"""
    def __init__(self, ticker: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticker '{ticker}' not found"
        )

class SearchError(FinancialDataException):
    """Raised when search operation fails"""
    def __init__(self, query: str, error: str):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed for query '{query}': {error}"
        )

class YFinanceError(FinancialDataException):
    """Raised when yfinance library encounters an error"""
    def __init__(self, operation: str, error: str):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"YFinance {operation} failed: {error}"
        ) 
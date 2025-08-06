from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class SearchResult(BaseModel):
    """Schema for search results"""
    symbol: str = Field(..., description="Stock ticker symbol")
    name: str = Field(..., description="Company name")
    exchange: Optional[str] = Field(None, description="Stock exchange")
    type: Optional[str] = Field(None, description="Instrument type")
    isin: Optional[str] = Field(None, description="ISIN code")
    country: Optional[str] = Field(None, description="Country of listing")

class SearchResponse(BaseModel):
    """Schema for search API response"""
    query: str = Field(..., description="Search query")
    results: List[SearchResult] = Field(..., description="Search results")
    total_count: int = Field(..., description="Total number of results")

class PriceData(BaseModel):
    """Schema for stock price data"""
    symbol: str = Field(..., description="Stock ticker symbol")
    current_price: Optional[float] = Field(None, description="Current stock price")
    previous_close: Optional[float] = Field(None, description="Previous closing price")
    open: Optional[float] = Field(None, description="Opening price")
    high: Optional[float] = Field(None, description="Day's high")
    low: Optional[float] = Field(None, description="Day's low")
    volume: Optional[int] = Field(None, description="Trading volume")
    market_cap: Optional[float] = Field(None, description="Market capitalization")
    pe_ratio: Optional[float] = Field(None, description="Price-to-earnings ratio")
    dividend_yield: Optional[float] = Field(None, description="Dividend yield")
    change: Optional[float] = Field(None, description="Price change")
    change_percent: Optional[float] = Field(None, description="Price change percentage")
    last_updated: Optional[datetime] = Field(None, description="Last update timestamp")

class CompanyInfo(BaseModel):
    """Schema for company information"""
    symbol: str = Field(..., description="Stock ticker symbol")
    name: str = Field(..., description="Company name")
    sector: Optional[str] = Field(None, description="Business sector")
    industry: Optional[str] = Field(None, description="Industry")
    country: Optional[str] = Field(None, description="Country of incorporation")
    website: Optional[str] = Field(None, description="Company website")
    description: Optional[str] = Field(None, description="Company description")
    employees: Optional[int] = Field(None, description="Number of employees")
    founded: Optional[int] = Field(None, description="Year founded")

class StockInfo(BaseModel):
    """Schema for comprehensive stock information"""
    symbol: str = Field(..., description="Stock ticker symbol")
    price_data: PriceData = Field(..., description="Current price information")
    company_info: CompanyInfo = Field(..., description="Company information")
    additional_data: Optional[Dict[str, Any]] = Field(None, description="Additional financial data")

class ErrorResponse(BaseModel):
    """Schema for error responses"""
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Detailed error information")
    status_code: int = Field(..., description="HTTP status code")

class HistoricalDataPoint(BaseModel):
    """Schema for a single point of historical price data"""
    date: datetime = Field(..., description="Date and time of the data point")
    open: Optional[float] = Field(None, description="Opening price")
    high: Optional[float] = Field(None, description="Highest price")
    low: Optional[float] = Field(None, description="Lowest price")
    close: Optional[float] = Field(None, description="Closing price")
    volume: Optional[int] = Field(None, description="Trading volume")
    dividends: Optional[float] = Field(None, description="Dividends paid")
    stock_splits: Optional[float] = Field(None, description="Stock splits")

class HistoricalDataResponse(BaseModel):
    """Schema for historical price data response"""
    symbol: str = Field(..., description="Stock ticker symbol")
    period: str = Field(..., description="Time period of the data")
    data: List[HistoricalDataPoint] = Field(..., description="List of historical data points")

class HealthCheck(BaseModel):
    """Schema for health check response"""
    status: str = Field(..., description="Service status")
    version: str = Field(..., description="API version")
    timestamp: datetime = Field(..., description="Current timestamp") 
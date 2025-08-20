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

class NewsArticle(BaseModel):
    """Schema for news articles related to stocks"""
    id: Optional[str] = Field(None, description="Unique identifier for the article")
    title: str = Field(..., description="Article title")
    publisher: Optional[str] = Field(None, description="News publisher")
    link: Optional[str] = Field(None, description="URL to the full article")
    published_at: Optional[datetime] = Field(None, description="Publication date and time")
    thumbnail: Optional[Dict[str, Any]] = Field(None, description="Thumbnail image information")
    related_tickers: List[str] = Field(default_factory=list, description="List of related ticker symbols")
    content_type: Optional[str] = Field(None, description="Type of content (ARTICLE, VIDEO, etc.)")
    summary: Optional[str] = Field(None, description="Short summary of the article")
    description: Optional[str] = Field(None, description="Full description or content preview")
    is_video: bool = Field(False, description="Whether the content is a video")

class BatchNewsRequest(BaseModel):
    """Schema for batch news request"""
    tickers: List[str] = Field(..., min_items=1, max_items=50, description="List of stock ticker symbols")
    limit_per_ticker: Optional[int] = Field(5, ge=1, le=20, description="Maximum number of news items per ticker")
    days: Optional[int] = Field(7, ge=1, le=30, description="Number of days to look back for news")

class TickerNews(BaseModel):
    """Schema for news related to a specific ticker"""
    ticker: str = Field(..., description="Stock ticker symbol")
    news: List[NewsArticle] = Field(..., description="List of news articles")

class BatchNewsResponse(BaseModel):
    """Schema for batch news response"""
    results: List[TickerNews] = Field(..., description="List of news by ticker")
    total_articles: int = Field(..., description="Total number of articles returned")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")

class StockInfo(BaseModel):
    """Schema for comprehensive stock information"""
    symbol: str = Field(..., description="Stock ticker symbol")
    price_data: PriceData = Field(..., description="Current price information")
    company_info: CompanyInfo = Field(..., description="Company information")
    news: List[NewsArticle] = Field(default_factory=list, description="List of recent news articles")
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

class MarketData(BaseModel):
    """Schema for market data"""
    symbol: str = Field(..., description="Stock ticker symbol")
    name: str = Field(..., description="Company name")
    price: Optional[float] = Field(None, description="Current price")
    change: Optional[float] = Field(None, description="Price change")
    change_percent: Optional[float] = Field(None, description="Price change percentage")
    volume: Optional[int] = Field(None, description="Trading volume")
    market_cap: Optional[float] = Field(None, description="Market capitalization")
    pe_ratio: Optional[float] = Field(None, description="Price-to-earnings ratio")


class MarketDataResponse(BaseModel):
    """Schema for market data response"""
    gainers: List[MarketData] = Field(..., description="Top gainers")
    losers: List[MarketData] = Field(..., description="Top losers")
    active: List[MarketData] = Field(..., description="Most active stocks")
    last_updated: datetime = Field(..., description="Last update timestamp")


class HealthCheck(BaseModel):
    """Schema for health check response"""
    status: str = Field(..., description="Service status")
    version: str = Field(..., description="API version")
    timestamp: datetime = Field(..., description="Current timestamp") 
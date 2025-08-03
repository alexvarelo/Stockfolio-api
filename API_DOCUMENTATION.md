# Stockfolio Financial Data API Documentation

## Overview

The Stockfolio Financial Data API provides access to real-time and historical financial market data using the yfinance library. This API allows you to search for financial instruments and retrieve detailed information about stocks, ETFs, and other securities.

## Base URL

```
http://localhost:8000
```

## Authentication

Currently, this API does not require authentication. All endpoints are publicly accessible.

## API Endpoints

### 1. Search Endpoints

#### Search for Financial Instruments

**Endpoint:** `GET /api/v1/search`

**Description:** Search for stocks, ETFs, and other financial instruments by name, ISIN, or ticker symbol.

**Parameters:**
- `query` (required): Search term (minimum 2 characters)
- `limit` (optional): Maximum number of results (1-100, default: 20)

**Example Request:**
```bash
curl "http://localhost:8000/api/v1/search?query=AAPL&limit=10"
```

**Example Response:**
```json
{
  "query": "AAPL",
  "results": [
    {
      "symbol": "AAPL",
      "name": "Apple Inc.",
      "exchange": "NMS",
      "type": "Stock",
      "isin": "US0378331005",
      "country": "US"
    }
  ],
  "total_count": 1
}
```

#### Get Popular Stocks

**Endpoint:** `GET /api/v1/search/popular`

**Description:** Get a list of popular and widely traded stocks.

**Example Request:**
```bash
curl "http://localhost:8000/api/v1/search/popular"
```

**Example Response:**
```json
[
  {
    "symbol": "AAPL",
    "name": "Apple Inc.",
    "exchange": "NMS",
    "type": "Stock",
    "isin": "US0378331005",
    "country": "US"
  },
  {
    "symbol": "MSFT",
    "name": "Microsoft Corporation",
    "exchange": "NMS",
    "type": "Stock",
    "isin": "US5949181045",
    "country": "US"
  }
]
```

#### Search by ISIN

**Endpoint:** `GET /api/v1/search/isin/{isin}`

**Description:** Search for a specific financial instrument by ISIN code.

**Parameters:**
- `isin` (path): The ISIN code to search for

**Example Request:**
```bash
curl "http://localhost:8000/api/v1/search/isin/US0378331005"
```

**Example Response:**
```json
{
  "symbol": "AAPL",
  "name": "Apple Inc.",
  "exchange": "NMS",
  "type": "Stock",
  "isin": "US0378331005",
  "country": "US"
}
```

### 2. Stock Information Endpoints

#### Get Comprehensive Stock Information

**Endpoint:** `GET /api/v1/stock/{ticker}`

**Description:** Get detailed information about a stock including price data and company information.

**Parameters:**
- `ticker` (path): Stock ticker symbol (e.g., AAPL, MSFT)

**Example Request:**
```bash
curl "http://localhost:8000/api/v1/stock/AAPL"
```

**Example Response:**
```json
{
  "symbol": "AAPL",
  "price_data": {
    "symbol": "AAPL",
    "current_price": 150.25,
    "previous_close": 149.80,
    "open": 150.00,
    "high": 151.50,
    "low": 149.50,
    "volume": 50000000,
    "market_cap": 2500000000000,
    "pe_ratio": 25.5,
    "dividend_yield": 0.5,
    "change": 0.45,
    "change_percent": 0.3,
    "last_updated": "2024-01-15T10:30:00"
  },
  "company_info": {
    "symbol": "AAPL",
    "name": "Apple Inc.",
    "sector": "Technology",
    "industry": "Consumer Electronics",
    "country": "US",
    "website": "https://www.apple.com",
    "description": "Apple Inc. designs, manufactures, and markets smartphones...",
    "employees": 164000,
    "founded": 1976
  },
  "additional_data": {
    // Additional yfinance data
  }
}
```

#### Get Stock Price Data

**Endpoint:** `GET /api/v1/stock/{ticker}/price`

**Description:** Get current price information for a stock.

**Parameters:**
- `ticker` (path): Stock ticker symbol

**Example Request:**
```bash
curl "http://localhost:8000/api/v1/stock/AAPL/price"
```

**Example Response:**
```json
{
  "symbol": "AAPL",
  "current_price": 150.25,
  "previous_close": 149.80,
  "open": 150.00,
  "high": 151.50,
  "low": 149.50,
  "volume": 50000000,
  "market_cap": 2500000000000,
  "pe_ratio": 25.5,
  "dividend_yield": 0.5,
  "change": 0.45,
  "change_percent": 0.3,
  "last_updated": "2024-01-15T10:30:00"
}
```

#### Get Company Information

**Endpoint:** `GET /api/v1/stock/{ticker}/info`

**Description:** Get detailed company information for a stock.

**Parameters:**
- `ticker` (path): Stock ticker symbol

**Example Request:**
```bash
curl "http://localhost:8000/api/v1/stock/AAPL/info"
```

**Example Response:**
```json
{
  "symbol": "AAPL",
  "name": "Apple Inc.",
  "sector": "Technology",
  "industry": "Consumer Electronics",
  "country": "US",
  "website": "https://www.apple.com",
  "description": "Apple Inc. designs, manufactures, and markets smartphones...",
  "employees": 164000,
  "founded": 1976
}
```

#### Get Historical Price Data

**Endpoint:** `GET /api/v1/stock/{ticker}/history`

**Description:** Get historical price data for a stock.

**Parameters:**
- `ticker` (path): Stock ticker symbol
- `period` (query): Time period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)

**Example Request:**
```bash
curl "http://localhost:8000/api/v1/stock/AAPL/history?period=1mo"
```

**Example Response:**
```json
{
  "ticker": "AAPL",
  "period": "1mo",
  "data": [
    {
      "Date": "2024-01-15",
      "Open": 150.00,
      "High": 151.50,
      "Low": 149.50,
      "Close": 150.25,
      "Volume": 50000000
    }
  ]
}
```

### 3. Utility Endpoints

#### Health Check

**Endpoint:** `GET /health`

**Description:** Check if the API is running and healthy.

**Example Request:**
```bash
curl "http://localhost:8000/health"
```

**Example Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2024-01-15T10:30:00"
}
```

#### API Information

**Endpoint:** `GET /api`

**Description:** Get API information and available endpoints.

**Example Request:**
```bash
curl "http://localhost:8000/api"
```

**Example Response:**
```json
{
  "name": "Stockfolio Financial Data API",
  "version": "1.0.0",
  "description": "Financial data API powered by yfinance",
  "endpoints": {
    "search": "/api/v1/search",
    "stock": "/api/v1/stock",
    "health": "/health"
  }
}
```

## Error Responses

The API returns standard HTTP status codes and error messages in JSON format:

### 400 Bad Request
```json
{
  "error": "Search query must be at least 2 characters long",
  "detail": "Search query must be at least 2 characters long",
  "status_code": 400
}
```

### 404 Not Found
```json
{
  "error": "Ticker 'INVALIDTICKER' not found",
  "detail": "Ticker 'INVALIDTICKER' not found",
  "status_code": 404
}
```

### 500 Internal Server Error
```json
{
  "error": "Internal server error",
  "detail": "Internal server error",
  "status_code": 500
}
```

### 503 Service Unavailable
```json
{
  "error": "YFinance get_ticker failed: Network error",
  "detail": "YFinance get_ticker failed: Network error",
  "status_code": 503
}
```

## Rate Limiting

The API includes basic rate limiting to prevent abuse. The default limit is 60 requests per minute per IP address.

## CORS

The API supports Cross-Origin Resource Sharing (CORS) and allows requests from any origin by default.

## Data Sources

This API uses the yfinance library to fetch data from Yahoo Finance. The data includes:

- Real-time stock prices
- Company information
- Historical price data
- Financial metrics (P/E ratio, market cap, etc.)
- Dividend information

## Usage Examples

### JavaScript/React Example

```javascript
// Search for stocks
const searchStocks = async (query) => {
  const response = await fetch(`http://localhost:8000/api/v1/search?query=${query}`);
  const data = await response.json();
  return data.results;
};

// Get stock information
const getStockInfo = async (ticker) => {
  const response = await fetch(`http://localhost:8000/api/v1/stock/${ticker}`);
  return await response.json();
};

// Get stock price
const getStockPrice = async (ticker) => {
  const response = await fetch(`http://localhost:8000/api/v1/stock/${ticker}/price`);
  return await response.json();
};
```

### Python Example

```python
import requests

# Search for stocks
def search_stocks(query):
    response = requests.get(f"http://localhost:8000/api/v1/search?query={query}")
    return response.json()

# Get stock information
def get_stock_info(ticker):
    response = requests.get(f"http://localhost:8000/api/v1/stock/{ticker}")
    return response.json()

# Get stock price
def get_stock_price(ticker):
    response = requests.get(f"http://localhost:8000/api/v1/stock/{ticker}/price")
    return response.json()
```

## Development

### Running the API

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the API:
   ```bash
   python start.py
   ```

3. Or using uvicorn directly:
   ```bash
   uvicorn app.main:app --reload
   ```

### Running Tests

```bash
pytest
```

### API Documentation

Once the API is running, you can access:

- **Interactive API docs (Swagger UI):** http://localhost:8000/docs
- **ReDoc documentation:** http://localhost:8000/redoc
- **OpenAPI specification:** http://localhost:8000/openapi.json

## Support

For issues or questions, please refer to the project documentation or create an issue in the repository. 
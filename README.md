# Stockfolio Financial Data API

A FastAPI-based financial data API that provides access to stock market information using the yfinance library.

## Features

- **Search Instruments**: Search for stocks, ETFs, and other financial instruments by name, ISIN, or ticker symbol
- **Stock Information**: Get detailed information about specific stocks including price data, company info, and financial metrics
- **Real-time Data**: Access current market data and historical information
- **RESTful API**: Clean, documented API endpoints for easy integration

## Quick Start

### Installation

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Running the API

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`

### API Documentation

Once running, visit:
- **Interactive API docs**: http://localhost:8000/docs
- **ReDoc documentation**: http://localhost:8000/redoc

## API Endpoints

### Search
- `GET /api/v1/search?query={search_term}` - Search for instruments by name, ISIN, or ticker

### Stock Information
- `GET /api/v1/stock/{ticker}` - Get detailed stock information
- `GET /api/v1/stock/{ticker}/price` - Get current price data
- `GET /api/v1/stock/{ticker}/info` - Get company information

## Project Structure

```
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application entry point
│   ├── api/
│   │   ├── __init__.py
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── endpoints/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── search.py
│   │   │   │   └── stock.py
│   │   │   └── api.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   └── exceptions.py
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py
│   └── services/
│       ├── __init__.py
│       ├── yfinance_service.py
│       └── search_service.py
├── tests/
│   ├── __init__.py
│   ├── test_search.py
│   └── test_stock.py
├── requirements.txt
└── README.md
```

## Development

### Running Tests

```bash
pytest
```

### Environment Variables

Create a `.env` file (optional):
```
DEBUG=True
API_V1_STR=/api/v1
PROJECT_NAME=Stockfolio Financial Data API
```

## Technologies Used

- **FastAPI**: Modern, fast web framework for building APIs
- **yfinance**: Yahoo Finance API wrapper for financial data
- **Pydantic**: Data validation using Python type annotations
- **Uvicorn**: ASGI server for running the FastAPI application

## License

MIT License 
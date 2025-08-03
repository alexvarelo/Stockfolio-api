import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_get_stock_info():
    """Test getting comprehensive stock information"""
    response = client.get("/api/v1/stock/AAPL")
    assert response.status_code == 200
    data = response.json()
    assert "symbol" in data
    assert "price_data" in data
    assert "company_info" in data
    assert data["symbol"] == "AAPL"

def test_get_stock_price():
    """Test getting stock price data"""
    response = client.get("/api/v1/stock/AAPL/price")
    assert response.status_code == 200
    data = response.json()
    assert "symbol" in data
    assert "current_price" in data
    assert data["symbol"] == "AAPL"

def test_get_company_info():
    """Test getting company information"""
    response = client.get("/api/v1/stock/AAPL/info")
    assert response.status_code == 200
    data = response.json()
    assert "symbol" in data
    assert "name" in data
    assert data["symbol"] == "AAPL"

def test_get_historical_data():
    """Test getting historical data"""
    response = client.get("/api/v1/stock/AAPL/history?period=1mo")
    assert response.status_code == 200
    data = response.json()
    assert "ticker" in data
    assert "period" in data
    assert "data" in data
    assert data["ticker"] == "AAPL"
    assert data["period"] == "1mo"

def test_get_stock_invalid_ticker():
    """Test getting stock info with invalid ticker"""
    response = client.get("/api/v1/stock/INVALIDTICKER")
    assert response.status_code == 404

def test_get_historical_data_invalid_period():
    """Test getting historical data with invalid period"""
    response = client.get("/api/v1/stock/AAPL/history?period=invalid")
    assert response.status_code == 400

def test_health_check():
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "version" in data
    assert "timestamp" in data
    assert data["status"] == "healthy"

def test_root_endpoint():
    """Test root endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "version" in data 
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_search_instruments():
    """Test search endpoint with valid query"""
    response = client.get("/api/v1/search?query=AAPL")
    assert response.status_code == 200
    data = response.json()
    assert "query" in data
    assert "results" in data
    assert "total_count" in data
    assert data["query"] == "AAPL"

def test_search_instruments_short_query():
    """Test search endpoint with short query"""
    response = client.get("/api/v1/search?query=A")
    assert response.status_code == 400

def test_search_instruments_empty_query():
    """Test search endpoint with empty query"""
    response = client.get("/api/v1/search?query=")
    assert response.status_code == 400

def test_get_popular_stocks():
    """Test popular stocks endpoint"""
    response = client.get("/api/v1/search/popular")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)

def test_search_by_isin():
    """Test ISIN search endpoint"""
    response = client.get("/api/v1/search/isin/US0378331005")  # Apple ISIN
    # This might return 404 if ISIN is not found, which is expected
    assert response.status_code in [200, 404]

def test_search_by_isin_short():
    """Test ISIN search with short ISIN"""
    response = client.get("/api/v1/search/isin/123")
    assert response.status_code == 400 
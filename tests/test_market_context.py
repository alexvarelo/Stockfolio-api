"""Market context tests: synthetic data, fixed seeds, no network."""
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.dependencies import get_current_client
from app.api.v1.endpoints.market import get_market_context_provider
from app.services import market_context as mc
from app.services import market_context_service as svc

DATES = pd.bdate_range("2024-01-01", periods=400)


def series(seed, start=100.0):
    r = np.random.default_rng(seed).normal(0.0003, 0.01, len(DATES))
    return pd.Series(start * np.cumprod(1 + r), index=DATES)


DATA = {"^VIX": series(1, 18), "^TNX": series(2, 4.2), "DX-Y.NYB": series(3, 104), "^GSPC": series(4, 5000)}


def fetcher(symbol):
    if symbol not in DATA:
        raise ValueError("boom")
    return DATA[symbol]


def test_percentile_edges():
    asc = pd.Series(np.arange(1.0, 101.0))
    assert mc.percentile_rank(asc) == 100.0
    assert mc.percentile_rank(asc[::-1].reset_index(drop=True)) == 0.0
    assert mc.percentile_rank(pd.Series([5.0, 5.0, 5.0, 5.0])) == 50.0
    assert mc.percentile_rank(pd.Series([1.0, 2.0, 2.0, 2.0])) == pytest.approx(66.7, abs=0.1)
    assert mc.percentile_rank(pd.Series([1.0])) is None


def test_percentile_window():
    s = pd.concat([pd.Series([1000.0] * 50), pd.Series(np.arange(252.0))], ignore_index=True)
    assert mc.percentile_rank(s) == 100.0  # old high outside the 252 window


def test_sma_distance():
    s = pd.Series(np.arange(1.0, 61.0))
    sma50 = s.tail(50).mean()
    assert mc.sma_distance(s, 50) == pytest.approx((60 / sma50 - 1) * 100, abs=0.01)
    assert mc.sma_distance(s, 200) is None


def test_change_1d():
    s = pd.Series([100.0, 102.0])
    assert mc.change_1d(s) == 2.0
    assert mc.change_1d(pd.Series([4.0, 4.25]), absolute=True) == 0.25


def test_compute_full():
    res = svc.compute_market_context(fetcher)
    assert [i.key for i in res.indicators] == ["vix", "us10y", "dxy", "sp500"]
    assert all(i.value is not None and 0 <= i.percentile_1y <= 100 for i in res.indicators)
    sp = res.indicators[3]
    assert sp.extra.sma50_distance is not None and sp.extra.sma200_distance is not None
    assert res.indicators[0].extra is None and len(sp.sparkline) == 60
    assert res.indicators[1].unit == "percent"
    assert res.breadth is None and any("breadth" in n for n in res.notes)
    assert res.as_of == DATES[-1].strftime("%Y-%m-%d")


def test_partial_failure():
    data = {k: v for k, v in DATA.items() if k != "^TNX"}
    res = svc.compute_market_context(lambda s: data[s] if s in data else (_ for _ in ()).throw(ValueError("x")))
    us = res.indicators[1]
    assert us.key == "us10y" and us.value is None and us.percentile_1y is None
    assert res.indicators[0].value is not None
    assert any("^TNX" in n for n in res.notes)


def test_partial_failure_not_cached():
    svc.market_cache.set("context", None)
    svc.market_cache._cache.clear()
    svc.get_market_context(lambda s: (_ for _ in ()).throw(ValueError("x")))
    assert svc.market_cache.get("context") is None
    svc.get_market_context(fetcher)
    assert svc.market_cache.get("context") is not None
    svc.market_cache._cache.clear()


@pytest.fixture
def client():
    svc.market_cache._cache.clear()
    app.dependency_overrides[get_current_client] = lambda: {"id": "test"}
    app.dependency_overrides[get_market_context_provider] = lambda: (lambda: svc.compute_market_context(fetcher))
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_endpoint_schema(client):
    r = client.get("/api/v1/market/context")
    assert r.status_code == 200, r.text
    d = r.json()
    assert set(d) == {"as_of", "indicators", "breadth", "notes", "disclaimer"}
    assert d["disclaimer"] == "Educational information, not financial advice."
    assert set(d["indicators"][0]) == {"key", "label", "symbol", "unit", "value", "change_1d",
                                       "percentile_1y", "sparkline", "extra", "reading"}
    assert d["indicators"][3]["extra"].keys() == {"sma50_distance", "sma200_distance"}


def test_endpoint_auth():
    app.dependency_overrides.clear()
    assert TestClient(app).get("/api/v1/market/context").status_code in (401, 403)

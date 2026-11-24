"""Technical indicator tests: synthetic deterministic data, no network."""
import json
import math

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.dependencies import get_current_client
from app.api.v1.endpoints.technicals import get_yfinance_service
from app.core.exceptions import TickerNotFoundError
from app.services import technicals as ta
from app.services.technicals_service import build_technicals


def make_df(n=800, seed=7, start=100.0):
    rng = np.random.default_rng(seed)
    close = start * np.cumprod(1 + rng.normal(0.0004, 0.012, n))
    idx = pd.bdate_range("2021-01-01", periods=n)
    return pd.DataFrame({
        "Open": close * 0.999, "High": close * 1.01, "Low": close * 0.99,
        "Close": close, "Volume": rng.integers(1_000, 5_000, n).astype(float),
    }, index=idx)


DF = make_df()
CLOSE = DF["Close"]


def test_sma_vs_loop():
    got = ta.sma(CLOSE, 20)
    assert got.iloc[:19].isna().all()
    for i in (19, 100, 500):
        assert got.iloc[i] == pytest.approx(np.mean(CLOSE.iloc[i - 19:i + 1]))


def test_ema_vs_loop():
    span = 12
    a = 2 / (span + 1)
    ref = [CLOSE.iloc[0]]
    for x in CLOSE.iloc[1:]:
        ref.append(a * x + (1 - a) * ref[-1])
    np.testing.assert_allclose(ta.ema(CLOSE, span).values, ref, rtol=1e-12)


def test_rsi_vs_hand_loop():
    c = CLOSE.iloc[:200]
    r = ta.rsi(c, 14)
    d = c.diff().values
    g = np.where(d > 0, d, 0.0)
    l = np.where(d < 0, -d, 0.0)
    ag, al = g[1], l[1]
    ref = {}
    for t in range(2, len(c)):
        ag = (13 / 14) * ag + g[t] / 14
        al = (13 / 14) * al + l[t] / 14
        ref[t] = 100 - 100 / (1 + ag / al)
    assert r.iloc[:14].isna().all()
    for t in range(14, 200):
        assert r.iloc[t] == pytest.approx(ref[t], abs=1e-6)


def test_rsi_wilder_textbook_sequence_in_range():
    # classic Wilder/StockCharts sequence; RSI stays within (0,100) and is high after the rally
    prices = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08,
              45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64]
    r = ta.rsi(pd.Series(prices), 14)
    assert r.iloc[14:].between(0, 100).all()


def test_rsi_100_on_rising_series():
    r = ta.rsi(pd.Series(np.arange(1.0, 60.0)), 14)
    assert (r.iloc[14:] == 100).all()


def test_macd_relations():
    m = ta.macd(CLOSE)
    np.testing.assert_allclose(m["macd"], ta.ema(CLOSE, 12) - ta.ema(CLOSE, 26))
    np.testing.assert_allclose(m["macd_signal"], ta.ema(m["macd"], 9))
    np.testing.assert_allclose(m["macd_hist"], m["macd"] - m["macd_signal"])


def test_bollinger():
    b = ta.bollinger(CLOSE)
    np.testing.assert_allclose(b["bb_middle"].dropna(), ta.sma(CLOSE, 20).dropna())
    sd = CLOSE.rolling(20).std(ddof=0)
    np.testing.assert_allclose((b["bb_upper"] - b["bb_lower"]).dropna(), (4 * sd).dropna())


def test_warmup_sma200_defined_at_first_point():
    res = build_technicals("X", "1y", DF, "USD")
    assert res.series[0].sma200 is not None
    assert res.series[0].sma50 is not None
    assert res.series[0].date > "2022-01-01"
    assert 240 < len(res.series) < 270
    assert res.latest.sma200 is not None and res.latest.above_sma200 is not None


def test_crossovers():
    idx = pd.bdate_range("2022-01-01", periods=300)
    # long decline then sharp rise: 50 crosses above 200 near the end
    vals = np.concatenate([np.linspace(200, 100, 250), np.linspace(100, 220, 50)])
    s = pd.Series(vals, index=idx)
    up = ta.recent_cross(ta.sma(s, 50), ta.sma(s, 200), 60)
    assert up["golden"] and not up["death"]
    vals2 = np.concatenate([np.linspace(100, 200, 250), np.linspace(200, 80, 50)])
    s2 = pd.Series(vals2, index=idx)
    down = ta.recent_cross(ta.sma(s2, 50), ta.sma(s2, 200), 60)
    assert down["death"] and not down["golden"]
    flat = pd.Series(np.full(300, 10.0), index=idx)
    assert ta.recent_cross(ta.sma(flat, 50), ta.sma(flat, 200)) == {"golden": False, "death": False}


def test_levels_zigzag():
    # peaks at 120, 121 (cluster), troughs 90, 80, ending at 100
    pts = [100, 90, 120, 80, 121, 100]
    vals = np.concatenate([np.linspace(pts[i], pts[i + 1], 11)[:-1] for i in range(len(pts) - 1)] + [[100.0]])
    s = pd.Series(vals, index=pd.bdate_range("2023-01-01", periods=len(vals)))
    lv = ta.support_resistance(s)
    assert lv["resistance"] == [pytest.approx(120.5)]
    assert lv["support"] == [pytest.approx(90.0), pytest.approx(80.0)]
    assert len(lv["support"]) <= 3


def test_no_nan_in_json():
    res = build_technicals("X", "6mo", make_df(60), "USD")  # short history: many nulls
    text = res.model_dump_json()
    assert "NaN" not in text and "Infinity" not in text
    json.loads(text, parse_constant=lambda c: pytest.fail(c))
    assert res.series[-1].sma200 is None


class FakeService:
    def get_daily_ohlcv(self, symbol, period="1y"):
        if symbol == "NOPE":
            raise TickerNotFoundError(symbol)
        return DF

    def get_currency(self, symbol):
        return "USD"


@pytest.fixture
def client():
    app.dependency_overrides[get_current_client] = lambda: {"id": "t"}
    app.dependency_overrides[get_yfinance_service] = lambda: FakeService()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_endpoint_schema(client):
    r = client.get("/api/v1/stock/aapl/technicals?period=1y")
    assert r.status_code == 200
    j = r.json()
    assert j["ticker"] == "AAPL" and j["period"] == "1y" and j["currency"] == "USD"
    assert j["disclaimer"] == "Educational information, not financial advice."
    assert {"date", "open", "high", "low", "close", "volume", "sma20", "sma50", "sma200", "ema12", "ema26",
            "rsi14", "macd", "macd_signal", "macd_hist", "bb_upper", "bb_middle", "bb_lower"} <= set(j["series"][0])
    assert {"above_sma50", "golden_cross_recent", "death_cross_recent", "avg_volume_20", "avg_volume_50"} <= set(j["latest"])
    assert len(j["levels"]["support"]) <= 3 and len(j["levels"]["resistance"]) <= 3
    assert j["as_of"] == j["series"][-1]["date"]


def test_endpoint_default_period_and_404(client):
    assert client.get("/api/v1/stock/AAPL/technicals").json()["period"] == "1y"
    assert client.get("/api/v1/stock/NOPE/technicals").status_code == 404


def test_endpoint_validation(client):
    assert client.get("/api/v1/stock/AAPL/technicals?period=10y").status_code == 422
    assert client.get("/api/v1/stock/BAD$TICK/technicals").status_code == 422
    assert client.get("/api/v1/stock/" + "A" * 21 + "/technicals").status_code == 422


def test_requires_auth():
    app.dependency_overrides.clear()
    assert TestClient(app).get("/api/v1/stock/AAPL/technicals").status_code in (401, 403)

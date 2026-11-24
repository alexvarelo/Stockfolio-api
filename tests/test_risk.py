"""Portfolio risk tests: synthetic data, fixed seeds, no network."""
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.dependencies import get_current_client
from app.api.v1.endpoints.portfolio import get_yfinance_service
from app.core.exceptions import TickerNotFoundError
from app.models.schemas import PortfolioRiskRequest
from app.services import risk
from app.services.portfolio_risk_service import compute_portfolio_risk

N = 120
DATES = pd.bdate_range("2024-01-01", periods=N)


def make_series(seed, drift=0.0005, vol=0.01, start=100.0):
    rng = np.random.default_rng(seed)
    r = rng.normal(drift, vol, N)
    return pd.Series(start * np.cumprod(1 + r), index=DATES)


A, B, BENCH = make_series(1), make_series(2, start=50.0), make_series(3, start=4000.0)
QTY = {"A": 10.0, "B": 40.0}


class FakeService:
    def __init__(self, data, currencies=None):
        self.data = data
        self.currencies = currencies or {}

    def get_daily_closes(self, symbol, period="1y"):
        if symbol not in self.data:
            raise TickerNotFoundError(symbol)
        return self.data[symbol]

    def get_currency(self, symbol):
        return self.currencies.get(symbol, "USD")


def test_hand_computed_metrics():
    prices = pd.DataFrame({"A": A, "B": B})
    rf = 0.02
    res = risk.compute_risk(prices, QTY, BENCH, rf)

    # manual numpy calc
    va, vb = A.to_numpy(), B.to_numpy()
    v = QTY["A"] * va + QTY["B"] * vb
    r = v[1:] / v[:-1] - 1
    b = BENCH.to_numpy()
    br = b[1:] / b[:-1] - 1
    beta = np.cov(r, br, ddof=1)[0, 1] / np.var(br, ddof=1)
    vol = np.std(r, ddof=1) * np.sqrt(252)
    peak = np.maximum.accumulate(v)
    mdd = (v / peak - 1).min()
    sharpe = np.mean(r - rf / 252) * 252 / vol
    w = np.array([QTY["A"] * va[-1], QTY["B"] * vb[-1]])
    w = w / w.sum()
    ra, rb = va[1:] / va[:-1] - 1, vb[1:] / vb[:-1] - 1
    c = np.corrcoef(ra, rb)[0, 1]
    ann = (v[-1] / v[0]) ** (252 / len(r)) - 1

    assert res["beta"] == pytest.approx(beta, abs=1e-9)
    assert res["volatility_annual"] == pytest.approx(vol, abs=1e-9)
    assert res["max_drawdown"] == pytest.approx(mdd, abs=1e-9)
    assert res["sharpe_ratio"] == pytest.approx(sharpe, abs=1e-9)
    assert res["annual_return"] == pytest.approx(ann, abs=1e-9)
    assert res["hhi"] == pytest.approx(float((w ** 2).sum()), abs=1e-9)
    assert res["effective_positions"] == pytest.approx(1 / (w ** 2).sum(), abs=1e-9)
    assert res["largest_position"]["weight"] == pytest.approx(w.max(), abs=1e-9)
    m = res["correlation"]["matrix"]
    assert m[0][1] == pytest.approx(c, abs=1e-9) and m[1][0] == pytest.approx(c, abs=1e-9)
    assert m[0][0] == pytest.approx(1.0, abs=1e-9)
    assert res["observations"] == N - 1


def test_known_drawdown():
    s = pd.Series([100, 120, 90, 95, 130], dtype=float)
    assert risk.max_drawdown(s) == pytest.approx(-0.25, abs=1e-12)


def test_insufficient_observations_gives_nulls_and_single_position_corr():
    prices = pd.DataFrame({"A": A.iloc[:10]})
    res = risk.compute_risk(prices, {"A": 5.0}, BENCH.iloc[:10])
    assert res["beta"] is None and res["volatility_annual"] is None and res["sharpe_ratio"] is None
    assert res["correlation"]["matrix"] == [[1.0]]
    assert res["hhi"] == pytest.approx(1.0)


def test_missing_ticker_reported_and_weights_renormalised():
    svc = FakeService({"A": A, "B": B, "^GSPC": BENCH})
    req = PortfolioRiskRequest(positions=[
        {"ticker": "A", "quantity": 10}, {"ticker": "B", "quantity": 40}, {"ticker": "ZZZ", "quantity": 3}])
    out = compute_portfolio_risk(req, svc)
    assert out.missing_tickers == ["ZZZ"]
    assert [w.ticker for w in out.weights] == ["A", "B"]
    assert sum(w.weight for w in out.weights) == pytest.approx(1.0, abs=1e-12)
    assert out.total_value == pytest.approx(10 * A.iloc[-1] + 40 * B.iloc[-1])


def test_fx_conversion_and_pence():
    fx = pd.Series(1.1, index=DATES)
    svc = FakeService(
        {"A": A, "UK.L": B * 100, "GBPUSD=X": fx * 0 + 1.25, "^GSPC": BENCH},
        {"UK.L": "GBp"},
    )
    req = PortfolioRiskRequest(positions=[{"ticker": "UK.L", "quantity": 2}])
    out = compute_portfolio_risk(req, svc)
    assert out.weights[0].value_base == pytest.approx(2 * B.iloc[-1] * 1.25)
    assert out.weights[0].currency == "GBp"


def test_ffill_aligns_holiday_gaps():
    gappy = B.drop(B.index[50:52])  # 2-day holiday mismatch
    df = risk.align_prices({"A": A, "B": gappy})
    assert len(df) == N


@pytest.fixture
def client():
    svc = FakeService({"A": A, "B": B, "^GSPC": BENCH})
    app.dependency_overrides[get_current_client] = lambda: {"id": "test"}
    app.dependency_overrides[get_yfinance_service] = lambda: svc
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_endpoint_schema(client):
    r = client.post("/api/v1/portfolio/risk", json={
        "positions": [{"ticker": "a", "quantity": 10}, {"ticker": "B", "quantity": 40}, {"ticker": "NOPE", "quantity": 1}],
        "risk_free_rate": 0.01})
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ["as_of", "period", "benchmark", "base_currency", "total_value", "weights", "beta",
              "volatility_annual", "annual_return", "max_drawdown", "sharpe_ratio", "largest_position",
              "hhi", "effective_positions", "correlation", "missing_tickers", "observations", "disclaimer"]:
        assert k in d
    assert d["period"] == "1y" and d["benchmark"] == "^GSPC" and d["base_currency"] == "USD"
    assert d["missing_tickers"] == ["NOPE"]
    assert set(d["weights"][0]) == {"ticker", "quantity", "price", "currency", "value_base", "weight"}
    assert d["correlation"]["tickers"] == ["A", "B"] and len(d["correlation"]["matrix"]) == 2
    assert d["disclaimer"] == "Educational information, not financial advice."


def test_endpoint_validation_and_auth(client):
    assert client.post("/api/v1/portfolio/risk", json={"positions": []}).status_code == 422
    assert client.post("/api/v1/portfolio/risk", json={"positions": [{"ticker": "A", "quantity": 0}]}).status_code == 422
    assert client.post("/api/v1/portfolio/risk", json={"positions": [{"ticker": "A", "quantity": 1}], "period": "9y"}).status_code == 422
    app.dependency_overrides.clear()
    assert TestClient(app).post("/api/v1/portfolio/risk", json={"positions": [{"ticker": "A", "quantity": 1}]}).status_code in (401, 403)

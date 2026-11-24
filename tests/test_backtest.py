"""Backtest tests: synthetic deterministic prices, no network."""
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints.strategies import get_yfinance_service
from app.core.dependencies import get_current_client
from app.main import app
from app.services import backtest as bt

IDX = pd.bdate_range("2020-01-01", "2020-12-31")


def df(**cols):
    return pd.DataFrame({k: pd.Series(v, index=IDX[:len(v)] if not isinstance(v, pd.Series) else v.index)
                         for k, v in cols.items()})


def const(price, index=IDX):
    return pd.Series(float(price), index=index)


def run(prices, strategy, weights, **kw):
    kw.setdefault("initial_capital", 0.0)
    return bt.run_backtest(prices, strategy, weights, prices.index[0], prices.index[-1], **kw)


def test_dca_constant_price():
    prices = pd.DataFrame({"A": const(50)})
    res = run(prices, "dca", {"A": 1.0}, monthly_amount=100.0)
    months = len(set(zip(IDX.year, IDX.month)))
    assert months == 12
    shares = sum(t["quantity"] for t in res["trades"])
    assert shares == pytest.approx(12 * 100 / 50)
    m = res["metrics"]["strategy"]
    assert m["total_invested"] == pytest.approx(1200)
    assert m["final_value"] == pytest.approx(1200)
    assert m["total_return"] == pytest.approx(0.0)
    assert m["cagr"] == pytest.approx(0.0, abs=1e-12)
    assert m["max_drawdown"] == pytest.approx(0.0)
    # invested only on first trading day of each month
    assert {t["date"].day for t in res["trades"]} <= {1, 2, 3}
    assert len(res["trades"]) == 12


def test_dca_benchmark_has_same_flows_and_values():
    rng = np.random.default_rng(1)
    prices = pd.DataFrame({"A": 100 * np.cumprod(1 + rng.normal(0, 0.01, len(IDX))),
                           "B": 50 * np.cumprod(1 + rng.normal(0, 0.01, len(IDX)))}, index=IDX)
    res = run(prices, "dca", {"A": 0.6, "B": 0.4}, initial_capital=500.0, monthly_amount=100.0)
    assert np.allclose(res["sim"]["invested"], res["bench"]["invested"])
    assert np.allclose(res["sim"]["flows"], res["bench"]["flows"])
    assert res["sim"]["invested"][-1] == pytest.approx(500 + 12 * 100)
    # DCA at weights is itself buy-and-hold of each contribution, so identical
    assert np.allclose(res["sim"]["values"], res["bench"]["values"])


def test_rebalance_hand_computed():
    idx = pd.bdate_range("2020-01-01", "2020-03-31")
    b = pd.Series(10.0, index=idx)
    b[(idx >= "2020-02-03") & (idx < "2020-03-02")] = 20.0
    prices = pd.DataFrame({"A": const(10, idx), "B": b})
    res = bt.run_backtest(prices, "rebalance", {"A": 1, "B": 1}, idx[0], idx[-1], 1000.0,
                          rebalance_frequency="monthly")
    # Feb 3: 500 A + 1000 B = 1500 -> 750/750 (75 A, 37.5 B). Mar 2: B back to 10 -> 750+375=1125
    assert res["metrics"]["strategy"]["final_value"] == pytest.approx(1125.0)
    # buy and hold: 50 A + 50 B at 10 -> 1000
    assert res["metrics"]["benchmark"]["final_value"] == pytest.approx(1000.0)
    sim = res["sim"]
    feb = list(idx).index(pd.Timestamp("2020-02-03"))
    assert sim["values"][feb] == pytest.approx(1500.0)
    assert sim["invested"][-1] == 1000.0
    # Feb rebalance: sell 25 B... buy 25 A -> 75 A held after
    feb_trades = {(t["ticker"], t["side"]): t["quantity"] for t in res["trades"] if t["date"] == idx[feb].date()}
    assert feb_trades[("A", "buy")] == pytest.approx(25.0)
    assert feb_trades[("B", "sell")] == pytest.approx(12.5)


def test_rebalance_period_starts_quarterly_count():
    prices = pd.DataFrame({"A": 100 + np.arange(len(IDX)) * 0.5, "B": const(20)}, index=IDX)
    res = run(prices, "rebalance", {"A": 1, "B": 1}, initial_capital=1000.0,
              rebalance_frequency="quarterly")
    days = {t["date"] for t in res["trades"] if t["date"] > IDX[0].date()}
    assert len(days) == 3  # Apr, Jul, Oct


def test_fees_reduce_value():
    prices = pd.DataFrame({"A": const(50)})
    res = run(prices, "dca", {"A": 1.0}, initial_capital=1000.0, fee_bps=100)
    m = res["metrics"]["strategy"]
    assert m["final_value"] == pytest.approx(1000 / 1.01)
    assert m["total_return"] == pytest.approx(1 / 1.01 - 1)
    assert res["trades"][0]["quantity"] == pytest.approx(1000 / 1.01 / 50)


def test_fees_on_signal_roundtrip():
    s = pd.Series([10.0] * 10, index=IDX[:10], name="A")
    buy = np.zeros(10, bool); sell = np.zeros(10, bool)
    buy[2] = True; sell[5] = True
    sim = bt.simulate_signals(s, buy, sell, 1000.0, fee_bps=50)
    assert sim["values"][-1] == pytest.approx(1000 / 1.005 * 0.995)
    assert [t["side"] for t in sim["trades"]] == ["buy", "sell"]


def test_twr_cagr_and_mdd_match_manual_despite_flows():
    p = pd.Series(np.concatenate([np.linspace(100, 150, 120), np.linspace(150, 90, 100),
                                  np.linspace(90, 130, len(IDX) - 220)]), index=IDX)
    res = run(pd.DataFrame({"A": p}), "dca", {"A": 1.0}, initial_capital=100.0, monthly_amount=50.0)
    m = res["metrics"]["strategy"]
    days = (IDX[-1] - IDX[0]).days
    assert m["cagr"] == pytest.approx((p.iloc[-1] / p.iloc[0]) ** (365.25 / days) - 1, rel=1e-9)
    assert m["max_drawdown"] == pytest.approx(float((p / p.cummax() - 1).min()), rel=1e-9)
    r = p.pct_change().dropna()
    assert m["volatility_annual"] == pytest.approx(r.std(ddof=1) * np.sqrt(252), rel=1e-9)
    assert m["time_in_market"] == pytest.approx(1.0)


def falling_then_rising():
    return pd.Series(np.concatenate([np.linspace(100, 60, 60), np.linspace(60, 160, 100)]),
                     index=IDX[:160], name="A")


def test_ma_cross_single_crossing_one_buy_next_day():
    p = falling_then_rising()
    prices = pd.DataFrame({"A": p})
    res = bt.run_backtest(prices, "ma_cross", {"A": 1}, p.index[0], p.index[-1], 1000.0, fast=5, slow=20)
    trades = res["trades"]
    assert [t["side"] for t in trades] == ["buy"]
    f, s = bt.sma(p, 5), bt.sma(p, 20)
    d = f - s
    k = int(np.where((d.shift(1) <= 0) & (d > 0))[0][0])
    assert trades[0]["date"] == p.index[k + 1].date()  # executed t+1
    assert trades[0]["price"] == pytest.approx(p.iloc[k + 1])
    assert trades[0]["quantity"] == pytest.approx(1000 / p.iloc[k + 1])
    assert 0 < res["metrics"]["strategy"]["time_in_market"] < 1
    # benchmark is buy and hold with same initial capital
    assert res["metrics"]["benchmark"]["total_invested"] == 1000.0
    assert res["metrics"]["benchmark"]["trades"] == 1


def test_ma_cross_sells_on_down_cross():
    p = pd.Series(np.concatenate([np.linspace(100, 60, 60), np.linspace(60, 160, 60),
                                  np.linspace(160, 50, 60)]), index=IDX[:180], name="A")
    res = bt.run_backtest(pd.DataFrame({"A": p}), "ma_cross", {"A": 1}, p.index[0], p.index[-1],
                          1000.0, fast=5, slow=20)
    assert [t["side"] for t in res["trades"]] == ["buy", "sell"]
    assert res["trades"][1]["date"] > res["trades"][0]["date"]


def test_rsi_wilder_basics():
    up = pd.Series(np.arange(1.0, 60.0))
    assert bt.rsi_wilder(up).iloc[-1] == pytest.approx(100.0)
    down = pd.Series(np.arange(60.0, 1.0, -1.0))
    assert bt.rsi_wilder(down).iloc[-1] == pytest.approx(0.0, abs=1e-9)


def test_rsi_trades_next_day_no_lookahead():
    p = pd.Series(np.concatenate([np.full(30, 100.0), np.linspace(100, 70, 30), np.linspace(70, 140, 60)]),
                  index=IDX[:120], name="A")
    p = p + np.sin(np.arange(120)) * 0.8  # deterministic noise
    res = bt.run_backtest(pd.DataFrame({"A": p}), "rsi", {"A": 1}, p.index[0], p.index[-1], 1000.0,
                          rsi_buy=30, rsi_sell=70)
    r = bt.rsi_wilder(p)
    kb = int(np.where((r.shift(1) >= 30) & (r < 30))[0][0])
    buy = res["trades"][0]
    assert buy["side"] == "buy"
    assert buy["date"] == p.index[kb + 1].date()
    assert buy["price"] == pytest.approx(p.iloc[kb + 1])
    ks = int(np.where((r.shift(1) <= 70) & (r > 70))[0][0])
    sell = res["trades"][1]
    assert sell["side"] == "sell" and sell["date"] == p.index[ks + 1].date()


def test_signal_on_last_day_not_executed():
    s = pd.Series([10.0] * 5, index=IDX[:5], name="A")
    buy = np.array([0, 0, 0, 0, 1], bool)
    sim = bt.simulate_signals(s, buy, np.zeros(5, bool), 100.0)
    assert sim["trades"] == []


def test_downsample_keeps_endpoints():
    idx = bt.downsample_indices(1200)
    assert len(idx) <= 500 and idx[0] == 0 and idx[-1] == 1199
    assert bt.downsample_indices(100) == list(range(100))
    long = pd.bdate_range("2010-01-01", "2024-12-31")
    prices = pd.DataFrame({"A": const(10, long)})
    res = run(prices, "dca", {"A": 1}, initial_capital=100.0)
    assert len(res["equity_curve"]) <= 500
    assert res["equity_curve"][0]["date"] == long[0].date()
    assert res["equity_curve"][-1]["date"] == long[-1].date()


def test_trades_capped_at_200():
    idx = pd.bdate_range("2000-01-03", "2020-12-31")
    prices = pd.DataFrame({"A": const(10, idx)})
    res = run(prices, "dca", {"A": 1}, monthly_amount=10.0)
    assert len(res["trades"]) == 200
    assert res["metrics"]["strategy"]["trades"] > 200


# ---------------- endpoint ----------------

class FakeService:
    def __init__(self, data, currencies=None):
        self.data = data
        self.currencies = currencies or {}

    def get_daily_closes(self, symbol, period="1y"):
        if symbol not in self.data:
            raise KeyError(symbol)
        return self.data[symbol]

    def get_currency(self, symbol):
        return self.currencies.get(symbol, "USD")


LONG = pd.bdate_range("2018-06-01", "2020-12-31")
RNG = np.random.default_rng(42)
A = pd.Series(100 * np.cumprod(1 + RNG.normal(0.0004, 0.01, len(LONG))), index=LONG)
B = pd.Series(50 * np.cumprod(1 + RNG.normal(0.0002, 0.012, len(LONG))), index=LONG)


@pytest.fixture
def client():
    svc = FakeService({"A": A, "B": B, "EURUSD=X": pd.Series(1.1, index=LONG)}, {"B": "EUR"})
    app.dependency_overrides[get_current_client] = lambda: {"id": "test"}
    app.dependency_overrides[get_yfinance_service] = lambda: svc
    yield TestClient(app)
    app.dependency_overrides.clear()


BASE = {"strategy": "dca", "tickers": [{"ticker": "A", "weight": 3}, {"ticker": "B", "weight": 1}],
        "start_date": "2019-01-02", "end_date": "2020-12-30", "initial_capital": 1000,
        "base_currency": "USD", "params": {"monthly_amount": 200}}


def test_endpoint_schema(client):
    r = client.post("/api/v1/strategies/backtest", json=BASE)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["strategy"] == "dca" and d["base_currency"] == "USD"
    assert d["start_date"] == "2019-01-02" and d["end_date"] == "2020-12-30"
    assert 2 <= len(d["equity_curve"]) <= 500
    assert set(d["equity_curve"][0]) == {"date", "strategy_value", "benchmark_value", "invested"}
    assert d["equity_curve"][0]["invested"] == pytest.approx(1200)
    for k in ("strategy", "benchmark"):
        assert set(d["metrics"][k]) == {"final_value", "total_invested", "total_return", "cagr",
                                        "max_drawdown", "volatility_annual", "trades", "time_in_market"}
    assert d["metrics"]["strategy"]["total_invested"] == pytest.approx(d["metrics"]["benchmark"]["total_invested"])
    assert d["trades"] and set(d["trades"][0]) == {"date", "ticker", "side", "quantity", "price"}
    assert any("Past performance" in n for n in d["notes"])
    assert d["disclaimer"] == "Educational information, not financial advice."
    # B (EUR) converted at 1.1: first trade price
    b0 = next(t for t in d["trades"] if t["ticker"] == "B")
    assert b0["price"] == pytest.approx(B.loc[b0["date"]] * 1.1)


def test_endpoint_ma_cross_and_rsi(client):
    for strat, params in (("ma_cross", {"fast": 10, "slow": 30}), ("rsi", {})):
        body = {**BASE, "strategy": strat, "tickers": [{"ticker": "A", "weight": 1}], "params": params}
        r = client.post("/api/v1/strategies/backtest", json=body)
        assert r.status_code == 200, r.text
        assert r.json()["metrics"]["strategy"]["total_invested"] == 1000


@pytest.mark.parametrize("patch", [
    {"strategy": "nope"},
    {"start_date": "1999-12-31"},
    {"start_date": "2019-13-01"},
    {"end_date": "2999-01-01"},
    {"end_date": "2019-02-01"},
    {"tickers": []},
    {"tickers": [{"ticker": "A", "weight": 0}]},
    {"tickers": [{"ticker": "A", "weight": -1}]},
    {"tickers": [{"ticker": "A", "weight": 1}, {"ticker": "A", "weight": 1}]},
    {"tickers": [{"ticker": f"T{i}", "weight": 1} for i in range(16)]},
    {"strategy": "rsi"},          # 2 tickers
    {"strategy": "ma_cross"},     # 2 tickers
    {"initial_capital": -1},
    {"fee_bps": 101},
    {"initial_capital": 0, "params": {"monthly_amount": 0}},
    {"strategy": "ma_cross", "tickers": [{"ticker": "A", "weight": 1}], "params": {"fast": 200, "slow": 50}},
    {"strategy": "rsi", "tickers": [{"ticker": "A", "weight": 1}], "params": {"rsi_buy": 80, "rsi_sell": 20}},
])
def test_validation_422(client, patch):
    r = client.post("/api/v1/strategies/backtest", json={**BASE, **patch})
    assert r.status_code == 422, r.text


def test_missing_ticker_data_is_422(client):
    body = {**BASE, "tickers": [{"ticker": "A", "weight": 1}, {"ticker": "ZZZ", "weight": 1}]}
    r = client.post("/api/v1/strategies/backtest", json=body)
    assert r.status_code == 422
    assert "ZZZ" in r.json()["detail"]


def test_history_starting_after_start_date_is_422(client):
    body = {**BASE, "start_date": "2018-06-04", "end_date": "2020-06-30"}
    svc = FakeService({"A": A, "B": B.iloc[200:], "EURUSD=X": pd.Series(1.1, index=LONG)}, {"B": "EUR"})
    app.dependency_overrides[get_yfinance_service] = lambda: svc
    r = client.post("/api/v1/strategies/backtest", json=body)
    assert r.status_code == 422 and "B" in r.json()["detail"]


def test_requires_auth():
    app.dependency_overrides.clear()
    assert TestClient(app).post("/api/v1/strategies/backtest", json=BASE).status_code in (401, 403)

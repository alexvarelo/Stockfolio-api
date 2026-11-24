"""Scenario tests: synthetic data, fixed seeds, no network."""
import os
import time

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.dependencies import get_current_client
from app.api.v1.endpoints.portfolio import get_yfinance_service
from app.core.exceptions import TickerNotFoundError
from app.models.scenarios import (
    StressRequest, MonteCarloRequest, WhatIfRequest, StressResponse, MonteCarloResponse, WhatIfResponse)
from app.services import scenarios as sc
from app.services import scenarios_service as svc


def rand_returns(seed, T=500, n=3, vol=0.01):
    return np.random.default_rng(seed).normal(0.0004, vol, (T, n))


def run(returns, v0, seed=1, paths=1000, days=252, c=0.0):
    idx = sc.bootstrap_indices(len(returns), paths, days, seed)
    return sc.simulate(returns, np.asarray(v0, float), idx, c)


# ---------- engine ----------
def test_determinism():
    r = rand_returns(0)
    a, b = run(r, [100, 200, 50], seed=7), run(r, [100, 200, 50], seed=7)
    c = run(r, [100, 200, 50], seed=8)
    assert np.array_equal(a["values"], b["values"])
    assert not np.array_equal(a["values"], c["values"])


def test_bootstrap_preserves_correlation():
    base = np.random.default_rng(3).normal(0, 0.01, 400)
    r = np.column_stack([base, 2 * base])
    s = sc.sample_returns(r, sc.bootstrap_indices(400, 50, 100, 5)).reshape(-1, 2)
    assert np.corrcoef(s.T)[0, 1] == pytest.approx(1.0, abs=1e-12)
    assert np.allclose(s[:, 1], 2 * s[:, 0])


def test_percentiles_monotonic_and_downsampled():
    out = sc.summarize(run(rand_returns(1), [100, 100, 100], days=5 * 252), 300.0, 0.0)
    assert len(out["percentiles"]) <= 260
    assert out["percentiles"][0]["day"] == 0 and out["percentiles"][-1]["day"] == 1260
    for p in out["percentiles"]:
        assert p["p5"] <= p["p25"] <= p["p50"] <= p["p75"] <= p["p95"]
    f = out["final"]
    assert f["p5"] <= f["p25"] <= f["p50"] <= f["p75"] <= f["p95"]


def test_zero_vol_deterministic_compounding():
    r = np.full((100, 2), 0.0005)
    sim = run(r, [1000.0, 500.0], days=252)
    expected = 1500.0 * 1.0005 ** 252
    assert sim["values"][:, -1] == pytest.approx(expected, rel=1e-4)
    out = sc.summarize(sim, 1500.0, 0.0)
    assert out["final"]["p5"] == pytest.approx(out["final"]["p95"], rel=1e-5)
    assert out["prob_loss"] == 0.0 and out["prob_drawdown_20"] == 0.0


def test_contributions_accounted():
    r = np.zeros((100, 2))  # flat prices
    sim = run(r, [600.0, 400.0], days=252, c=100.0)
    assert sc.n_contributions(252) == 12
    assert sim["values"][:, -1] == pytest.approx(1000.0 + 1200.0, rel=1e-5)
    out = sc.summarize(sim, 1000.0, 1200.0)
    assert out["prob_loss"] == 0.0  # final == start + contributions
    # pro-rata: growth only on asset 0 -> contribution weights follow current weights
    r2 = np.column_stack([np.full(100, 0.001), np.zeros(100)])
    s2 = run(r2, [500.0, 500.0], days=42, c=100.0)
    a0 = 500 * 1.001 ** 21
    w0 = a0 / (a0 + 500)
    a0 = (a0 + 100 * w0) * 1.001 ** 21
    a1 = 500 + 100 * (1 - w0)
    a0b, a1b = a0, a1
    w1 = a0b / (a0b + a1b)
    # second contribution split at day-42 weights
    assert s2["values"][:, -1] == pytest.approx(a0b + a1b + 100, rel=1e-4)
    assert w1 > w0


def test_drawdown_detected():
    r = np.full((50, 1), -0.01)
    sim = run(r, [100.0], days=63)
    assert (sim["min_drawdown"] <= -0.2).all()  # 0.99**63 - 1 ~ -0.47


def test_window_return_coverage():
    idx = pd.bdate_range("2020-01-01", "2020-12-31")
    s = pd.Series(np.linspace(100, 200, len(idx)), index=idx)
    assert sc.window_return(s, "2020-02-19", "2020-03-23") is not None
    assert sc.window_return(s, "2019-06-01", "2020-03-23") is None  # starts mid-window
    assert sc.clamp_beta(None) == 1.0 and sc.clamp_beta(5) == 3.0 and sc.clamp_beta(-1) == 0.0


@pytest.mark.skipif(os.environ.get("SKIP_TIMING_TESTS"), reason="timing test disabled")
def test_mc_timing_15_positions_5000_paths_5y():
    r = rand_returns(11, T=1250, n=15, vol=0.015)
    idx = sc.bootstrap_indices(len(r), 5000, 5 * 252, 42)
    t0 = time.perf_counter()
    sim = sc.simulate(r, np.full(15, 1000.0), idx, 100.0)
    sc.summarize(sim, 15000.0, 6000.0)
    elapsed = time.perf_counter() - t0
    print(f"MC timing: {elapsed:.2f}s")
    assert elapsed < 3.0


# ---------- service with fake data ----------
class FakeService:
    def __init__(self, data, currencies=None):
        self.data, self.currencies = data, currencies or {}

    def get_daily_closes(self, symbol, period="1y"):
        if symbol not in self.data:
            raise TickerNotFoundError(symbol)
        return self.data[symbol]

    def get_currency(self, symbol):
        return self.currencies.get(symbol, "USD")


def prices_from(seed, dates, start=100.0, vol=0.01, drift=0.0003):
    r = np.random.default_rng(seed).normal(drift, vol, len(dates))
    return pd.Series(start * np.cumprod(1 + r), index=dates)


LONG = pd.bdate_range("2007-01-01", "2024-12-31")
SHORT = pd.bdate_range("2021-06-01", "2024-12-31")


def stress_service():
    bench = prices_from(1, LONG, 1000.0)
    old = prices_from(2, LONG, 50.0)
    new = prices_from(3, SHORT, 20.0)
    return FakeService({"^GSPC": bench, "OLD": old, "NEW": new}), bench, old, new


def test_stress_historical_vs_beta_proxy_and_shocks():
    service, bench, old, new = stress_service()
    req = StressRequest(positions=[{"ticker": "OLD", "quantity": 10}, {"ticker": "NEW", "quantity": 20}],
                        base_currency="USD")
    out = svc.compute_stress(req, service)
    keys = [s.key for s in out.scenarios]
    assert keys == ["gfc_2008", "covid_2020", "bear_2022", "shock_-10", "shock_-20", "shock_-30"]
    covid = out.scenarios[1]
    pos = {p.ticker: p for p in covid.positions}
    assert pos["OLD"].method == "historical"
    exp = old.loc["2020-02-19":"2020-03-23"]
    assert pos["OLD"].ret == pytest.approx(exp.iloc[-1] / exp.iloc[0] - 1)
    assert pos["NEW"].method == "beta_proxy"  # no data before 2021
    assert covid.method == "beta_proxy"
    assert out.scenarios[2].positions[1].method == "historical"  # bear_2022 is covered by NEW
    b = covid.benchmark_return
    assert b == pytest.approx(bench.loc["2020-02-19":"2020-03-23"].iloc[-1] / bench.loc["2020-02-19":"2020-03-23"].iloc[0] - 1)
    assert pos["NEW"].ret == pytest.approx(pos["NEW"].ret)  # beta*b below
    shock = out.scenarios[4]
    assert shock.method == "shock" and shock.benchmark_return == -0.2
    for p in shock.positions:
        beta = pos["NEW"].ret / b if p.ticker == "NEW" else None
        assert p.method == "shock"
    # shock = (1+shock)^beta - 1, beta consistent across scenarios and exposed per position
    beta_new = pos["NEW"].beta
    assert pos["OLD"].beta is None                       # historical => no beta
    assert pos["NEW"].ret == pytest.approx((1 + b) ** beta_new - 1)
    sp = {p.ticker: p for p in shock.positions}
    assert sp["NEW"].beta == pytest.approx(beta_new)
    assert sp["NEW"].ret == pytest.approx(0.8 ** beta_new - 1)
    assert 0 <= beta_new <= 3
    assert shock.portfolio_return == pytest.approx(sum(p.weight * p.ret for p in shock.positions))
    assert shock.value_after == pytest.approx(out.current_value * (1 + shock.portfolio_return), abs=0.02)
    assert shock.pnl == pytest.approx(shock.value_after - out.current_value, abs=0.02)


def test_weekly_beta_recovers_known_beta_and_defaults():
    d = pd.bdate_range("2022-01-03", periods=520)
    b = prices_from(1, d, 1000.0, vol=0.01)
    s = b ** 1.0  # same path => beta ~1 on weekly returns
    assert sc.weekly_beta(s, b) == pytest.approx(1.0, abs=1e-6)
    assert sc.weekly_beta(b.iloc[-100:] * 2, b) == pytest.approx(1.0, abs=1e-6)  # ~20 weeks => default
    short = pd.bdate_range("2024-01-01", periods=120)  # 24 weeks < 52
    bs = prices_from(1, short, 1000.0)
    assert sc.weekly_beta(prices_from(5, short), bs) == 1.0
    assert sc.proxy_return(2.0, -0.1) == pytest.approx(0.81 - 1)
    assert sc.proxy_return(3.0, -0.9) >= -1.0


def mc_service():
    d = pd.bdate_range("2019-01-01", periods=900)
    data = {"^GSPC": prices_from(1, d, 1000.0), "A": prices_from(2, d), "B": prices_from(3, d, 50.0),
            "C": prices_from(4, d, 30.0)}
    return FakeService(data)


POS = [{"ticker": "A", "quantity": 10}, {"ticker": "B", "quantity": 20}]


def test_mc_service_deterministic():
    s = mc_service()
    req = MonteCarloRequest(positions=POS, paths=1000, monthly_contribution=50)
    a, b = svc.compute_montecarlo(req, s), svc.compute_montecarlo(req, s)
    assert a.model_dump() == b.model_dump()
    assert a.seed == 42 and a.total_contributions == 600
    c = svc.compute_montecarlo(req.model_copy(update={"seed": 1}), s)
    assert c.final != a.final


def test_whatif_identical_portfolios_delta_zero():
    s = mc_service()
    req = WhatIfRequest(current=MonteCarloRequest(positions=POS, paths=1000), changes={})
    out = svc.compute_whatif(req, s)
    assert out.delta.p50 == 0 and out.delta.p5 == 0 and out.delta.prob_loss == 0
    assert out.current == out.modified
    # sell all of B + buy C changes things
    req2 = WhatIfRequest(current=MonteCarloRequest(positions=POS, paths=1000),
                         changes={"sell": [{"ticker": "B", "quantity": 20}], "buy": [{"ticker": "C", "quantity": 5}]})
    out2 = svc.compute_whatif(req2, s)
    assert out2.delta.p50 != 0
    assert out2.cash_from_sales > 0 and out2.delta.p50_return is not None
    assert out2.risk_modified.hhi != out2.risk_current.hhi


def test_whatif_sell_more_than_held_422():
    s = mc_service()
    req = WhatIfRequest(current=MonteCarloRequest(positions=POS, paths=1000),
                        changes={"sell": [{"ticker": "A", "quantity": 11}]})
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        svc.compute_whatif(req, s)
    assert e.value.status_code == 422


def test_whatif_sale_proceeds_kept_as_cash():
    s = mc_service()
    px = svc.load_base_series(["A", "B"], "USD", "5y", s)[0]
    last_b = float(px["B"].iloc[-1])
    cur = MonteCarloRequest(positions=POS, paths=1000)
    out = svc.compute_whatif(WhatIfRequest(current=cur, changes={"sell": [{"ticker": "B", "quantity": 10}]}), s)
    assert out.cash_from_sales == pytest.approx(10 * last_b, abs=0.01)
    # money is conserved at day 0: start_value of the modified portfolio includes the cash
    assert out.modified.start_value == pytest.approx(out.current.start_value, abs=0.02)
    assert out.risk_modified.hhi > 0
    # selling everything of one asset and buying nothing: start value still the same
    out2 = svc.compute_whatif(WhatIfRequest(current=cur, changes={"sell": [{"ticker": "B", "quantity": 20}]}), s)
    assert out2.modified.start_value == pytest.approx(out2.current.start_value, abs=0.02)
    # return-based delta uses each portfolio's own money in
    m, c = out.modified, out.current
    exp = (m.final.p50 / (m.start_value + m.total_contributions)) - (c.final.p50 / (c.start_value + c.total_contributions))
    assert out.delta.p50_return == pytest.approx(exp, abs=1e-4)


def test_cash_not_given_contributions_and_zero_return():
    r = rand_returns(3, T=300, n=2)
    r = np.concatenate([r, np.zeros((300, 1))], axis=1)
    idx = sc.bootstrap_indices(300, 200, 63, 1)
    sim = sc.simulate(r, np.array([100.0, 0.0, 500.0]), idx, 10.0, no_contrib=np.array([False, False, True]))
    cash_only = sc.simulate(np.zeros((300, 1)), np.array([500.0]), idx, 0.0)
    assert (cash_only["values"] == 500.0).all()
    # risky part must receive 3 x 10 of contributions: total >= cash + contributions-ish > 500
    assert sim["values"][:, -1].min() > 500.0
    # all-zero risky + cash: contribution lands in cash
    sim2 = sc.simulate(np.zeros((300, 2)), np.array([0.0, 500.0]), idx, 10.0, no_contrib=np.array([False, True]))
    assert np.allclose(sim2["values"][:, -1], 530.0)


def test_whatif_short_history_held_ticker_excluded_but_bought_required():
    d = pd.bdate_range("2019-01-01", periods=900)
    data = {"^GSPC": prices_from(1, d, 1000.0), "A": prices_from(2, d), "C": prices_from(4, d, 30.0),
            "S": prices_from(9, d[-100:], 10.0)}
    s = FakeService(data)
    cur = MonteCarloRequest(positions=[{"ticker": "A", "quantity": 10}, {"ticker": "S", "quantity": 5}], paths=1000)
    out = svc.compute_whatif(WhatIfRequest(current=cur, changes={"buy": [{"ticker": "C", "quantity": 1}]}), s)
    assert {(e.ticker, e.reason) for e in out.excluded} == {("S", "short_history")}
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        svc.compute_whatif(WhatIfRequest(current=cur, changes={"buy": [{"ticker": "S", "quantity": 1}]}), s)
    assert e.value.status_code == 422


def test_non_positive_prices_dropped_or_excluded():
    d = pd.bdate_range("2019-01-01", periods=900)
    bad = prices_from(2, d)
    bad.iloc[400] = 0.0
    allneg = pd.Series(-1.0, index=d)
    s = FakeService({"^GSPC": prices_from(1, d, 1000.0), "A": prices_from(3, d), "Z": bad, "N": allneg})
    out = svc.compute_montecarlo(MonteCarloRequest(
        positions=[{"ticker": "A", "quantity": 1}, {"ticker": "Z", "quantity": 1}, {"ticker": "N", "quantity": 1}],
        paths=1000), s)
    assert [(e.ticker, e.reason) for e in out.excluded] == [("N", "invalid_prices")]
    assert np.isfinite(out.final.p50)


def test_whatif_ticker_union_cap_and_budget():
    s = mc_service()
    from fastapi import HTTPException
    many = [{"ticker": f"T{i}", "quantity": 1} for i in range(31)]
    with pytest.raises(HTTPException) as e:
        svc.compute_whatif(WhatIfRequest(current=MonteCarloRequest(positions=many, paths=1000), changes={}), s)
    assert e.value.status_code == 422 and "30" in e.value.detail
    with pytest.raises(HTTPException) as e:
        svc._check_budget(10000, 1260, 50)
    assert e.value.status_code == 422


# ---------- endpoints ----------
@pytest.fixture
def client():
    app.dependency_overrides[get_current_client] = lambda: {"id": "test"}
    app.dependency_overrides[get_yfinance_service] = lambda: mc_service()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_endpoint_schemas(client):
    r = client.post("/api/v1/scenarios/montecarlo", json={"positions": POS, "paths": 1000})
    assert r.status_code == 200
    body = r.json()
    MonteCarloResponse(**body)
    assert body["disclaimer"] == "Educational information, not financial advice."
    assert set(body["final"]) == {"p5", "p25", "p50", "p75", "p95", "mean"}

    r = client.post("/api/v1/scenarios/whatif", json={
        "current": {"positions": POS, "paths": 1000}, "changes": {"buy": [{"ticker": "C", "quantity": 3}]}})
    assert r.status_code == 200
    WhatIfResponse(**r.json())
    assert set(r.json()["risk_current"]) == {"volatility_annual", "beta", "max_drawdown", "hhi"}

    r = client.post("/api/v1/scenarios/whatif", json={
        "current": {"positions": POS}, "changes": {"sell": [{"ticker": "A", "quantity": 99}]}})
    assert r.status_code == 422


def test_stress_endpoint_schema_and_return_alias(client):
    service, *_ = stress_service()
    app.dependency_overrides[get_yfinance_service] = lambda: service
    r = client.post("/api/v1/scenarios/stress", json={"positions": [{"ticker": "OLD", "quantity": 5}]})
    assert r.status_code == 200
    body = r.json()
    StressResponse(**body)
    assert "return" in body["scenarios"][0]["positions"][0]
    assert body["scenarios"][-1]["method"] == "shock"


@pytest.mark.parametrize("url,body", [
    ("montecarlo", {"positions": POS, "seed": -1}),
    ("montecarlo", {"positions": POS, "seed": 2**32}),
    ("montecarlo", {"positions": POS, "seed": 10**30}),
    ("montecarlo", {"positions": [{"ticker": "A", "quantity": 1e308}]}),
    ("montecarlo", {"positions": [{"ticker": "A", "quantity": 2e9}]}),
    ("montecarlo", {"positions": POS, "monthly_contribution": 1e308}),
    ("montecarlo", {"positions": POS, "base_currency": "XYZ"}),
    ("stress", {"positions": [{"ticker": "A", "quantity": 1e308}]}),
    ("stress", {"positions": POS, "base_currency": "ZZZ"}),
    ("whatif", {"current": {"positions": POS, "paths": 5001}, "changes": {}}),
    ("whatif", {"current": {"positions": POS}, "changes": {"buy": [{"ticker": "C", "quantity": 1e308}]}}),
    ("whatif", {"current": {"positions": POS}, "changes": {"monthly_contribution": 1e300}}),
    ("whatif", {"current": {"positions": POS, "seed": -5}, "changes": {}}),
])
def test_former_500s_are_422(client, url, body):
    r = client.post(f"/api/v1/scenarios/{url}", json=body)
    assert r.status_code == 422, r.text


def test_non_finite_overflow_is_422_not_500(client):
    # valid per-field bounds but price x quantity overflows -> safety net
    d = pd.bdate_range("2019-01-01", periods=900)
    huge = FakeService({"^GSPC": prices_from(1, d, 1000.0), "A": prices_from(2, d, 1e305)})
    app.dependency_overrides[get_yfinance_service] = lambda: huge
    for url, body in [("montecarlo", {"positions": [{"ticker": "A", "quantity": 1e9}]}),
                      ("stress", {"positions": [{"ticker": "A", "quantity": 1e9}]})]:
        r = client.post(f"/api/v1/scenarios/{url}", json=body)
        assert r.status_code == 422 and "Non-finite" in r.json()["detail"], r.text


def test_shocks_deduplicated(client):
    service, *_ = stress_service()
    app.dependency_overrides[get_yfinance_service] = lambda: service
    r = client.post("/api/v1/scenarios/stress", json={"positions": [{"ticker": "OLD", "quantity": 5}],
                                                      "shocks": [-0.2, -0.2, -0.20001]})
    assert r.status_code == 200
    assert [s["key"] for s in r.json()["scenarios"] if s["key"].startswith("shock")] == ["shock_-20"]


def test_montecarlo_budget_422(client):
    d = pd.bdate_range("2019-01-01", periods=900)
    data = {"^GSPC": prices_from(1, d, 1000.0), **{f"T{i}": prices_from(i + 2, d) for i in range(40)}}
    app.dependency_overrides[get_yfinance_service] = lambda: FakeService(data)
    pos = [{"ticker": f"T{i}", "quantity": 1} for i in range(40)]
    r = client.post("/api/v1/scenarios/montecarlo", json={"positions": pos, "paths": 10000, "horizon_years": 5})
    assert r.status_code == 422 and "too large" in r.json()["detail"]


def test_validation_and_auth(client):
    url = "/api/v1/scenarios/montecarlo"
    for body in [{"positions": []}, {"positions": POS, "paths": 10}, {"positions": POS, "horizon_years": 6},
                 {"positions": POS, "lookback": "1y"}, {"positions": POS, "monthly_contribution": -1},
                 {"positions": [{"ticker": "A", "quantity": 0}]}, {"positions": POS, "base_currency": "EURO"}]:
        assert client.post(url, json=body).status_code == 422, body
    assert client.post("/api/v1/scenarios/stress", json={"positions": POS, "shocks": [-1.5]}).status_code == 422
    app.dependency_overrides.pop(get_current_client)
    assert TestClient(app).post(url, json={"positions": POS}).status_code in (401, 403)

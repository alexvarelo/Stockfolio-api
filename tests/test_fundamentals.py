"""Fundamentals tests: synthetic yfinance-shaped DataFrames, fixed values, no network."""
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.dependencies import get_current_client
from app.core.exceptions import TickerNotFoundError
from app.api.v1.endpoints import analysis as analysis_ep
from app.models.analysis import FinancialsResponse, HealthResponse
from app.services import fundamentals as fm
from app.services import fundamentals_service as fs

A_DATES = [pd.Timestamp("2023-12-31"), pd.Timestamp("2024-12-31")]
Q_DATES = list(pd.date_range("2024-03-31", periods=4, freq="QE"))


def df(rows, dates):
    """rows: name -> values oldest first. Returned like yfinance: newest column first."""
    d = pd.DataFrame({k: pd.Series(v, index=dates) for k, v in rows.items()}).T
    return d[sorted(d.columns, reverse=True)]


def stm(inc=None, bal=None, cf=None, dates=A_DATES):
    e = {}
    return fm.Frames(df(inc, dates) if inc else None, df(bal, dates) if bal else None,
                     df(cf, dates) if cf else None)


def status(m):
    return m.status


# ---------------------------------------------------------------- financials

def test_items_fcf_margins_net_debt():
    fr = stm(
        inc={"Total Revenue": [1000, 2000], "Gross Profit": [400, 1000], "Operating Income": [100, 400],
             "Net Income": [50, 300], "EBITDA": [150, 500]},
        bal={"Cash Cash Equivalents And Short Term Investments": [200, 500], "Total Debt": [300, 400],
             "Ordinary Shares Number": [100, 98]},
        cf={"Operating Cash Flow": [120, 600], "Capital Expenditure": [-20, -150]})
    items = fm.build_items(fr, 5)
    assert [i.period_end.isoformat() for i in items] == ["2023-12-31", "2024-12-31"]
    i = items[1]
    assert i.free_cash_flow == 450 and items[0].free_cash_flow == 100
    assert (i.gross_margin, i.operating_margin, i.net_margin) == (0.5, 0.2, 0.15)
    assert i.net_debt == -100 and items[0].net_debt == 100
    assert i.shares_outstanding == 98 and i.ebitda == 500


def test_aliases_and_missing_rows():
    fr = stm(inc={"Operating Revenue": [0, 0]},
             bal={"Cash And Cash Equivalents": [10, 20], "Other Short Term Investments": [5, 5],
                  "Long Term Debt And Capital Lease Obligation": [50, 60]},
             cf={"Free Cash Flow": [7, 8]})
    i = fm.build_items(fr, 5)[1]
    assert i.revenue == 0 and i.gross_margin is None and i.net_margin is None  # zero revenue
    assert i.cash == 25 and i.total_debt == 60 and i.net_debt == 35
    assert i.free_cash_flow == 8 and i.capex is None and i.ebitda is None


def test_limit_and_all_null_period_dropped():
    dates = list(pd.date_range("2018-12-31", periods=7, freq="YE"))
    fr = fm.Frames(df({"Total Revenue": [np.nan] + list(range(1, 7))}, dates))
    items = fm.build_items(fr, 5)
    assert len(items) == 5 and items[-1].revenue == 6 and items[0].revenue == 2


# ---------------------------------------------------------------- health

def quarterly_state(fcf, cash=1000.0, shares=None, ebitda=None, debt=0.0, ebit=None, interest=None):
    n = 4
    cf = {"Operating Cash Flow": list(fcf), "Capital Expenditure": [0.0] * n}
    inc = {}
    if ebitda is not None:
        inc["EBITDA"] = [ebitda] * n
    if ebit is not None:
        inc["Operating Income"] = [ebit] * n
    if interest is not None:
        inc["Interest Expense"] = [interest] * n
    bal = {"Cash Cash Equivalents And Short Term Investments": [cash] * n, "Total Debt": [debt] * n}
    if shares:
        bal["Ordinary Shares Number"] = shares
    return fm.Statements(quarterly=fm.Frames(df(inc, Q_DATES) if inc else None, df(bal, Q_DATES), df(cf, Q_DATES)))


def test_cash_runway():
    m = fm.cash_runway(quarterly_state([-100, -100, -100, -100], cash=800))
    assert m.value == pytest.approx(24.0) and m.status == "good"  # 800/100 quarters * 3
    m = fm.cash_runway(quarterly_state([-100, -100, -100, -100], cash=400))
    assert m.value == pytest.approx(12.0) and m.status == "warn"
    assert fm.cash_runway(quarterly_state([-100] * 4, cash=100)).status == "bad"
    m = fm.cash_runway(quarterly_state([-50, 20, 30, 10]))  # average FCF positive
    assert m.value is None and m.status == "good" and m.explanation == "Generates cash; no burn"


def test_dilution():
    base = [100.0, 100.0, 100.0, 100.0]
    # quarter dates are ~91 days apart so 3 quarters back is ~273d; use annual for 1y
    st = fm.Statements(annual=fm.Frames(None, df({"Ordinary Shares Number": [100.0, 101.5]}, A_DATES), None))
    assert (fm.dilution_yoy(st).value, fm.dilution_yoy(st).status) == (pytest.approx(1.5), "good")
    st = fm.Statements(annual=fm.Frames(None, df({"Ordinary Shares Number": [100.0, 108.0]}, A_DATES), None))
    assert fm.dilution_yoy(st).status == "warn"
    st = fm.Statements(annual=fm.Frames(None, df({"Ordinary Shares Number": [100.0, 120.0]}, A_DATES), None))
    assert fm.dilution_yoy(st).status == "bad"
    st = fm.Statements(annual=fm.Frames(None, df({"Ordinary Shares Number": [100.0, 95.0]}, A_DATES), None))
    m = fm.dilution_yoy(st)
    assert m.value == pytest.approx(-5.0) and m.status == "good"  # buyback
    assert fm.dilution_yoy(fm.Statements()).status == "na"


def test_net_debt_to_ebitda():
    f = fm.net_debt_to_ebitda
    m = f(quarterly_state([0] * 4, cash=100, debt=500, ebitda=100))  # TTM EBITDA 400, ND 400 -> 1.0
    assert m.value == pytest.approx(1.0) and m.status == "good"
    m = f(quarterly_state([0] * 4, cash=100, debt=1300, ebitda=100))  # 1200/400 = 3
    assert m.value == pytest.approx(3.0) and m.status == "warn"
    assert f(quarterly_state([0] * 4, cash=100, debt=2100, ebitda=100)).status == "bad"  # 5
    m = f(quarterly_state([0] * 4, cash=900, debt=100, ebitda=100))  # net cash
    assert m.status == "good" and m.value < 0
    m = f(quarterly_state([0] * 4, cash=0, debt=100, ebitda=-10))
    assert m.status == "bad" and m.value is None
    assert f(quarterly_state([0] * 4, cash=0, debt=100, ebitda=None)).status == "na"


def test_interest_coverage():
    f = fm.interest_coverage
    m = f(quarterly_state([0] * 4, ebit=60, interest=-10))  # 240/40 = 6
    assert m.value == pytest.approx(6.0) and m.status == "good"
    assert f(quarterly_state([0] * 4, ebit=30, interest=10)).status == "warn"  # 3
    assert f(quarterly_state([0] * 4, ebit=20, interest=10)).status == "bad"  # 2
    m = f(quarterly_state([0] * 4, ebit=20, interest=0))
    assert m.status == "good" and m.value is None
    m = f(quarterly_state([0] * 4, ebit=20, debt=0.0))  # no interest row, no debt
    assert m.status == "good"
    assert f(quarterly_state([0] * 4, ebit=20, debt=50.0)).status == "na"


def test_interest_coverage_negative_ebit_text():
    m = fm.interest_coverage(quarterly_state([0] * 4, ebit=-20, interest=10))
    assert m.status == "bad" and m.explanation == "Operating result is negative, so it does not cover interest."


def altman_state(**over):
    bal = {"Total Assets": [1000.0], "Total Liabilities Net Minority Interest": [400.0],
           "Working Capital": [200.0], "Retained Earnings": [300.0]}
    inc = {"EBIT": [100.0], "Total Revenue": [800.0]}
    for k, v in over.items():
        (bal if k in bal else inc)[k] = [v]
    d = [pd.Timestamp("2024-12-31")]
    return fm.Statements(annual=fm.Frames(df(inc, d), df(bal, d), None))


def test_altman_hand_computed():
    m = fm.altman_z(altman_state(), 1200.0)
    expected = 1.2 * 0.2 + 1.4 * 0.3 + 3.3 * 0.1 + 0.6 * 3.0 + 1.0 * 0.8  # 3.59
    assert m.value == pytest.approx(expected) and m.value == pytest.approx(3.59)
    assert m.status == "good" and "manufacturers" in m.explanation
    assert fm.altman_z(altman_state(), 300.0).status == "warn"  # 1.79+... = 2.15
    assert fm.altman_z(altman_state(**{"Retained Earnings": -300.0}), 100.0).status == "bad"
    m = fm.altman_z(altman_state(), None)
    assert m.status == "na" and m.value is None and "market cap" in m.explanation


def test_altman_unit_distinct_from_piotroski():
    assert fm.altman_z(altman_state(), 1200.0).unit == "ratio"
    assert fm.altman_z(altman_state(), None).unit == "ratio"
    assert fm.piotroski_f(piotroski_state(PREV, CUR_ALL_PASS)).unit == "score"


def test_altman_currency_mismatch_na():
    m = fm.altman_z(altman_state(), 1200.0, currency_mismatch=True)
    assert m.status == "na" and m.value is None and "currency mismatch" in m.explanation.lower()


def _info(cur, mcap=1000.0):
    return {"currency": cur, "marketCap": mcap}


def test_market_cap_conversion():
    st = fm.Statements(financial_currency="USD")
    rate = lambda a, b: {("GBP", "USD"): 1.25}.get((a, b))  # noqa: E731
    assert fs.market_cap_for_altman(_info("USD"), st, None, rate) == (1000.0, False)
    # GBp quote -> treated as GBP (marketCap already in GBP)
    assert fs.market_cap_for_altman(_info("GBp"), st, None, rate) == (1250.0, False)
    assert fs.market_cap_for_altman(_info("TWD"), st, None, rate) == (None, True)
    assert fs.market_cap_for_altman(_info("EUR"), fm.Statements(), None, rate) == (1000.0, False)


def test_market_cap_fx_via_service():
    idx = pd.to_datetime(["2025-01-30", "2025-01-31"])
    svc = FakeSvc({"TWDUSD=X": pd.Series([0.03, 0.031], index=idx)})
    st = fm.Statements(financial_currency="USD")
    v, mis = fs.market_cap_for_altman(_info("TWD", 1e6), st, svc)
    assert not mis and v == pytest.approx(31000.0)
    assert fs.market_cap_for_altman(_info("CHF"), st, svc) == (None, True)


def test_compare_price_zero_not_missing(monkeypatch):
    monkeypatch.setattr(fs, "get_info", lambda t: {"currency": "USD", "currentPrice": 0.0,
                                                   "regularMarketPrice": 7.0})
    monkeypatch.setattr(fs, "get_statements", lambda t, info=None: fm.Statements())
    svc = FakeSvc({"AAA": _hist(1, 5, 6)})
    assert fs.compute_compare(["AAA"], svc).rows[0].price == 0.0


def test_stray_quarterly_column_dropped():
    dates = list(pd.date_range("2024-03-31", periods=3, freq="QE"))
    fr = fm.Frames(df({"Total Revenue": [10.0, 20.0, np.nan], "Gross Profit": [1.0, 2.0, 3.0]}, dates))
    items = fm.build_items(fr, 8)
    assert [i.revenue for i in items] == [10.0, 20.0]


def piotroski_state(y0, y1):
    keys = ["Net Income", "Total Revenue", "Gross Profit"]
    # three periods: the oldest only supplies opening total assets for y0 (same as y0's)
    d3 = [pd.Timestamp("2022-12-31")] + A_DATES
    inc = {k: [np.nan, y0[k], y1[k]] for k in keys}
    bal = {k: [y0[k], y0[k], y1[k]] for k in ["Total Assets", "Long Term Debt", "Current Assets",
                                               "Current Liabilities", "Ordinary Shares Number"]}
    cf = {"Operating Cash Flow": [np.nan, y0["Operating Cash Flow"], y1["Operating Cash Flow"]]}
    return fm.Statements(annual=fm.Frames(df(inc, d3), df(bal, d3), df(cf, d3)))


PREV = {"Net Income": 50.0, "Total Revenue": 1000.0, "Gross Profit": 300.0, "Total Assets": 1000.0,
        "Long Term Debt": 300.0, "Current Assets": 400.0, "Current Liabilities": 300.0,
        "Ordinary Shares Number": 100.0, "Operating Cash Flow": 60.0}
CUR_ALL_PASS = {"Net Income": 100.0, "Total Revenue": 1200.0, "Gross Profit": 420.0, "Total Assets": 1000.0,
                "Long Term Debt": 200.0, "Current Assets": 500.0, "Current Liabilities": 300.0,
                "Ordinary Shares Number": 100.0, "Operating Cash Flow": 150.0}


def test_piotroski():
    m = fm.piotroski_f(piotroski_state(PREV, CUR_ALL_PASS))
    assert m.value == 9 and m.status == "good"
    # more shares + lower gross margin -> fails tests 7 and 8 -> 7 (still good)
    cur = dict(CUR_ALL_PASS, **{"Ordinary Shares Number": 110.0, "Gross Profit": 300.0})
    m = fm.piotroski_f(piotroski_state(PREV, cur))
    assert m.value == 7 and m.status == "good"
    # additionally: OCF < NI (test 4), higher leverage (5), lower current ratio (6) -> 4 (warn)
    cur.update({"Operating Cash Flow": 90.0, "Long Term Debt": 400.0, "Current Assets": 300.0})
    m = fm.piotroski_f(piotroski_state(PREV, cur))
    assert m.value == 4 and m.status == "warn"
    # losses everywhere
    bad = dict(PREV, **{"Net Income": -10.0, "Operating Cash Flow": -5.0, "Total Revenue": 900.0,
                        "Long Term Debt": 400.0, "Current Assets": 300.0, "Gross Profit": 200.0,
                        "Ordinary Shares Number": 120.0})
    m = fm.piotroski_f(piotroski_state(PREV, bad))
    assert m.value <= 3 and m.status == "bad"


def test_piotroski_partial_and_missing():
    st = fm.Statements(annual=fm.Frames(
        df({"Net Income": [10.0, 20.0]}, A_DATES), df({"Total Assets": [100.0, 100.0]}, A_DATES), None))
    m = fm.piotroski_f(st)  # only ROA>0 available (needs opening assets)
    assert m.status == "na" and m.value == 1 and "only 1 of 9 tests available" in m.explanation
    assert fm.piotroski_f(fm.Statements()).status == "na"


def test_health_empty_never_raises():
    ms = fm.compute_health(fm.Statements(), None)
    assert [m.key for m in ms] == ["cash_runway_months", "dilution_yoy", "net_debt_to_ebitda",
                                   "interest_coverage", "altman_z", "piotroski_f"]
    assert all(m.status == "na" and m.value is None and m.explanation for m in ms)


# ---------------------------------------------------------------- compare

class FakeSvc:
    def __init__(self, closes, currency="USD"):
        self.closes, self.cur = closes, currency

    def get_daily_closes(self, symbol, period="1y"):
        if symbol not in self.closes:
            raise TickerNotFoundError(symbol)
        return self.closes[symbol]

    def get_currency(self, symbol):
        return self.cur if symbol in self.closes else None


def _hist(years, start, end):
    idx = pd.bdate_range(end=pd.Timestamp("2025-01-31"), periods=int(years * 261))
    return pd.Series(np.linspace(start, end, len(idx)), index=idx)


@pytest.fixture
def patched(monkeypatch):
    infos = {
        "AAA": {"shortName": "Alpha", "currency": "USD", "currentPrice": 10.0, "marketCap": 1e9,
                "trailingPE": 20.0, "grossMargins": 0.5, "revenueGrowth": 0.1, "currentRatio": 1.5},
        "EUR1": {"shortName": "Euro Co", "currency": "EUR", "regularMarketPrice": 5.0, "marketCap": 2e9},
    }
    monkeypatch.setattr(fs, "get_info", lambda t: infos.get(t, {}))
    monkeypatch.setattr(fs, "get_statements", lambda t, info=None: fm.Statements())
    closes = {"AAA": _hist(5.2, 50, 100), "EUR1": _hist(2, 10, 20),
              "EURUSD=X": pd.Series([1.0, 1.1], index=pd.to_datetime(["2025-01-30", "2025-01-31"]))}
    return FakeSvc(closes)


def test_compare_missing_ticker_and_fx(patched):
    res = fs.compute_compare(["AAA", "EUR1", "ZZZ"], patched)
    assert res.missing == ["ZZZ"] and [r.ticker for r in res.rows] == ["AAA", "EUR1"]
    a, e = res.rows
    assert a.market_cap_usd == 1e9 and a.valuation.pe == 20.0 and a.health.current_ratio == 1.5
    assert a.returns.r5y == pytest.approx(0.9275, abs=1e-3) and a.returns.r1y is not None
    assert e.market_cap_usd == pytest.approx(2e9 * 1.1) and e.price == 5.0
    assert e.returns.r1y is not None and e.returns.r3y is None and e.returns.r5y is None
    assert e.health.altman_z is None


def test_price_return_exact():
    idx = pd.to_datetime(["2023-01-31", "2024-01-31", "2025-01-31"])
    s = pd.Series([100.0, 150.0, 120.0], index=idx)
    assert fs._price_return(s, 1) == pytest.approx(120 / 150 - 1)
    assert fs._price_return(s, 2) == pytest.approx(0.2)
    assert fs._price_return(s, 3) is None


# ---------------------------------------------------------------- endpoints

@pytest.fixture
def client(patched):
    app.dependency_overrides[get_current_client] = lambda: {"id": "test"}
    app.dependency_overrides[analysis_ep.get_yfinance_service] = lambda: patched
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_financials_and_health_endpoints(client, monkeypatch):
    fr = stm(inc={"Total Revenue": [1000, 2000]}, cf={"Operating Cash Flow": [1, 2], "Capital Expenditure": [-1, -1]})
    st = fm.Statements(annual=fr, financial_currency="EUR")
    monkeypatch.setattr(fs, "get_statements", lambda t, info=None: st)
    r = client.get("/api/v1/stock/aapl/financials?period=annual")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "AAPL" and body["currency"] == "EUR" and body["period"] == "annual"
    assert body["disclaimer"] == "Educational information, not financial advice."
    assert set(body["items"][0]) == set(FinancialsResponse.model_json_schema()["$defs"]["FinancialItem"]["properties"])
    assert body["items"][1]["free_cash_flow"] == 1
    assert client.get("/api/v1/stock/AAPL/financials?period=weekly").status_code == 422

    r = client.get("/api/v1/stock/AAPL/health")
    assert r.status_code == 200
    h = r.json()
    assert h["as_of"] == "2024-12-31" and len(h["metrics"]) == 6
    assert {m["status"] for m in h["metrics"]} <= {"good", "warn", "bad", "na"}
    HealthResponse(**h)


def test_compare_endpoint(client):
    r = client.get("/api/v1/compare?tickers=aaa,eur1,AAA,zzz")
    assert r.status_code == 200
    b = r.json()
    assert b["tickers"] == ["AAA", "EUR1", "ZZZ"] and b["missing"] == ["ZZZ"] and b["base_currency"] == "USD"
    assert set(b["rows"][0]) >= {"valuation", "growth", "margins", "health", "returns", "market_cap_usd"}


@pytest.mark.parametrize("url", [
    "/api/v1/stock/BAD%20TICKER/financials", "/api/v1/stock/$$/health",
    "/api/v1/stock/" + "A" * 21 + "/health",
    "/api/v1/compare?tickers=AAPL", "/api/v1/compare?tickers=A,B,C,D,E,F,G", "/api/v1/compare?tickers=A,A",
    "/api/v1/compare?tickers=A,B$", "/api/v1/compare",
])
def test_validation_422(client, url):
    assert client.get(url).status_code == 422

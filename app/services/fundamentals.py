"""Pure fundamentals maths on yfinance-shaped statement DataFrames (rows = line items,
columns = period-end timestamps). No network access."""
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from app.models.analysis import FinancialItem, HealthMetric, DISCLAIMER  # noqa: F401

# field -> ordered (statement, yfinance row name) candidates. Single place for row-name variants.
ALIASES: Dict[str, List[Tuple[str, str]]] = {
    "revenue": [("income", "Total Revenue"), ("income", "Operating Revenue"), ("income", "Revenue")],
    "gross_profit": [("income", "Gross Profit")],
    "operating_income": [("income", "Operating Income"), ("income", "Total Operating Income As Reported")],
    "net_income": [("income", "Net Income"), ("income", "Net Income Common Stockholders"),
                   ("income", "Net Income Including Noncontrolling Interests"),
                   ("income", "Net Income From Continuing Operation Net Minority Interest")],
    "ebitda": [("income", "EBITDA"), ("income", "Normalized EBITDA")],
    "ebit": [("income", "EBIT"), ("income", "Operating Income")],
    "interest_expense": [("income", "Interest Expense"), ("income", "Interest Expense Non Operating")],
    "operating_cash_flow": [("cashflow", "Operating Cash Flow"),
                            ("cashflow", "Cash Flow From Continuing Operating Activities"),
                            ("cashflow", "Total Cash From Operating Activities")],
    "capex": [("cashflow", "Capital Expenditure"), ("cashflow", "Capital Expenditures"),
              ("cashflow", "Purchase Of PPE")],
    "reported_fcf": [("cashflow", "Free Cash Flow")],
    "cash_combined": [("balance", "Cash Cash Equivalents And Short Term Investments")],
    "cash_only": [("balance", "Cash And Cash Equivalents"), ("balance", "Cash Financial"),
                  ("balance", "Cash")],
    "short_term_investments": [("balance", "Other Short Term Investments"),
                               ("balance", "Short Term Investments")],
    "total_debt": [("balance", "Total Debt")],
    "debt_long": [("balance", "Long Term Debt And Capital Lease Obligation"), ("balance", "Long Term Debt")],
    "debt_short": [("balance", "Current Debt And Capital Lease Obligation"), ("balance", "Current Debt")],
    "long_term_debt": [("balance", "Long Term Debt"), ("balance", "Long Term Debt And Capital Lease Obligation")],
    "shares": [("balance", "Ordinary Shares Number"), ("balance", "Share Issued"),
               ("income", "Diluted Average Shares"), ("income", "Basic Average Shares")],
    "total_assets": [("balance", "Total Assets")],
    "total_liabilities": [("balance", "Total Liabilities Net Minority Interest"), ("balance", "Total Liabilities")],
    "current_assets": [("balance", "Current Assets"), ("balance", "Total Current Assets")],
    "current_liabilities": [("balance", "Current Liabilities"), ("balance", "Total Current Liabilities")],
    "working_capital": [("balance", "Working Capital")],
    "retained_earnings": [("balance", "Retained Earnings")],
}


def _num(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


@dataclass
class Frames:
    """Statements for one frequency. Columns are sorted oldest first."""
    income: pd.DataFrame = field(default_factory=pd.DataFrame)
    balance: pd.DataFrame = field(default_factory=pd.DataFrame)
    cashflow: pd.DataFrame = field(default_factory=pd.DataFrame)

    def __post_init__(self):
        for name in ("income", "balance", "cashflow"):
            df = getattr(self, name)
            if df is None or df.empty:
                df = pd.DataFrame()
            else:
                df = df.loc[:, ~df.columns.duplicated()]
                df = df.reindex(sorted(df.columns), axis=1)
            setattr(self, name, df)

    def is_empty(self) -> bool:
        return self.income.empty and self.balance.empty and self.cashflow.empty

    def periods(self) -> List[pd.Timestamp]:
        cols = set()
        for df in (self.income, self.balance, self.cashflow):
            cols.update(df.columns)
        return sorted(cols)


@dataclass
class Statements:
    annual: Frames = field(default_factory=Frames)
    quarterly: Frames = field(default_factory=Frames)
    financial_currency: Optional[str] = None

    def is_empty(self) -> bool:
        return self.annual.is_empty() and self.quarterly.is_empty()


def _raw(fr: Frames, name: str, col) -> Optional[float]:
    for stmt, row in ALIASES[name]:
        df = getattr(fr, stmt)
        if not df.empty and row in df.index and col in df.columns:
            v = df.loc[row, col]
            if isinstance(v, pd.Series):
                v = v.iloc[0]
            v = _num(v)
            if v is not None:
                return v
    return None


def val(fr: Frames, name: str, col) -> Optional[float]:
    """Value of a (possibly derived) field for one period; None when unavailable."""
    if name == "cash":
        c = _raw(fr, "cash_combined", col)
        if c is not None:
            return c
        c = _raw(fr, "cash_only", col)
        if c is None:
            return None
        return c + (_raw(fr, "short_term_investments", col) or 0.0)
    if name == "total_debt":
        d = _raw(fr, "total_debt", col)
        if d is not None:
            return d
        lt, st = _raw(fr, "debt_long", col), _raw(fr, "debt_short", col)
        if lt is None and st is None:
            return None
        return (lt or 0.0) + (st or 0.0)
    if name == "free_cash_flow":
        ocf, cx = _raw(fr, "operating_cash_flow", col), _raw(fr, "capex", col)
        if ocf is not None and cx is not None:
            return ocf - abs(cx)
        return _raw(fr, "reported_fcf", col)
    if name == "net_debt":
        d, c = val(fr, "total_debt", col), val(fr, "cash", col)
        return None if d is None or c is None else d - c
    if name == "working_capital":
        w = _raw(fr, "working_capital", col)
        if w is not None:
            return w
        ca, cl = _raw(fr, "current_assets", col), _raw(fr, "current_liabilities", col)
        return None if ca is None or cl is None else ca - cl
    if name == "capex":
        return _raw(fr, "capex", col)
    return _raw(fr, name, col)


def _margin(num: Optional[float], rev: Optional[float]) -> Optional[float]:
    if num is None or rev is None or rev == 0:
        return None
    return num / rev


def build_items(fr: Frames, n: int) -> List[FinancialItem]:
    """Last `n` periods, oldest first; periods lacking revenue, net income, operating cash flow
    and cash are dropped."""
    out: List[FinancialItem] = []
    for col in fr.periods():
        rev = val(fr, "revenue", col)
        gp, oi, ni = val(fr, "gross_profit", col), val(fr, "operating_income", col), val(fr, "net_income", col)
        data = dict(
            revenue=rev, gross_profit=gp, operating_income=oi, net_income=ni,
            gross_margin=_margin(gp, rev), operating_margin=_margin(oi, rev), net_margin=_margin(ni, rev),
            operating_cash_flow=val(fr, "operating_cash_flow", col), capex=val(fr, "capex", col),
            free_cash_flow=val(fr, "free_cash_flow", col), cash=val(fr, "cash", col),
            total_debt=val(fr, "total_debt", col), net_debt=val(fr, "net_debt", col),
            shares_outstanding=val(fr, "shares", col), ebitda=val(fr, "ebitda", col),
        )
        if all(v is None for v in (rev, ni, data["operating_cash_flow"], data["cash"])):
            continue  # nearly-empty period (e.g. stray quarterly column)
        out.append(FinancialItem(period_end=pd.Timestamp(col).date(), **data))
    return out[-n:]


# ---------------------------------------------------------------- health

def _m(key, label, unit, value, status, explanation) -> HealthMetric:
    return HealthMetric(key=key, label=label, unit=unit, value=value, status=status, explanation=explanation)


def _na(key, label, unit, why) -> HealthMetric:
    return _m(key, label, unit, None, "na", why)


def _ttm(fr: Frames, name: str) -> Optional[float]:
    cols = fr.periods()[-4:]
    if len(cols) < 4:
        return None
    vals = [val(fr, name, c) for c in cols]
    return None if any(v is None for v in vals) else float(sum(vals))


def _ttm_or_annual(st: Statements, name: str) -> Optional[float]:
    t = _ttm(st.quarterly, name)
    if t is not None:
        return t
    cols = st.annual.periods()
    return val(st.annual, name, cols[-1]) if cols else None


def _latest(fr: Frames, name: str) -> Optional[float]:
    for col in reversed(fr.periods()):
        v = val(fr, name, col)
        if v is not None:
            return v
    return None


def _latest_bs(st: Statements, name: str) -> Optional[float]:
    v = _latest(st.quarterly, name)
    return v if v is not None else _latest(st.annual, name)


def cash_runway(st: Statements) -> HealthMetric:
    key, label = "cash_runway_months", "Cash runway"
    per_q = 1.0
    fcfs = [v for v in (val(st.quarterly, "free_cash_flow", c) for c in st.quarterly.periods()[-4:])
            if v is not None]
    if not fcfs:  # e.g. semi-annual reporters: fall back to annual FCF (/4 per quarter)
        per_q = 4.0
        fcfs = [v for v in (val(st.annual, "free_cash_flow", c) for c in st.annual.periods()[-2:])
                if v is not None]
    if not fcfs:
        return _na(key, label, "months", "Free cash flow data is not available.")
    avg = sum(fcfs) / len(fcfs) / per_q
    if avg >= 0:
        return _m(key, label, "months", None, "good", "Generates cash; no burn")
    cash = _latest_bs(st, "cash")
    if cash is None:
        return _na(key, label, "months", "Cash balance is not available.")
    months = max(cash, 0.0) / (-avg) * 3.0
    status = "good" if months >= 24 else "warn" if months >= 12 else "bad"
    return _m(key, label, "months", months, status,
              f"Cash covers about {months:.0f} months at the recent average quarterly burn.")


def dilution_yoy(st: Statements) -> HealthMetric:
    key, label = "dilution_yoy", "Share dilution (YoY)"
    pts: Dict[pd.Timestamp, float] = {}
    for fr in (st.annual, st.quarterly):  # quarterly overrides on equal dates
        for c in fr.periods():
            v = val(fr, "shares", c)
            if v is not None and v > 0:
                pts[pd.Timestamp(c)] = v
    if len(pts) < 2:
        return _na(key, label, "percent", "Share count history is not available.")
    last = max(pts)
    target = last - pd.Timedelta(days=365)
    prev = min((d for d in pts if d < last), key=lambda d: abs((d - target).days))
    if abs((prev - target).days) > 75:
        return _na(key, label, "percent", "No share count about one year earlier is available.")
    chg = (pts[last] / pts[prev] - 1) * 100
    status = "good" if chg <= 2 else "warn" if chg <= 10 else "bad"
    word = "increased" if chg > 0 else "decreased"
    return _m(key, label, "percent", chg, status,
              f"Share count {word} {abs(chg):.1f}% versus about a year earlier.")


def net_debt_to_ebitda(st: Statements) -> HealthMetric:
    key, label = "net_debt_to_ebitda", "Net debt / EBITDA"
    debt, cash = _latest_bs(st, "total_debt"), _latest_bs(st, "cash")
    ebitda = _ttm_or_annual(st, "ebitda")
    if debt is None or cash is None:
        return _na(key, label, "x", "Debt or cash balance is not available.")
    nd = debt - cash
    if nd <= 0:
        v = nd / ebitda if ebitda and ebitda > 0 else None
        return _m(key, label, "x", v, "good", "Holds more cash than debt (net cash).")
    if ebitda is None:
        return _na(key, label, "x", "EBITDA is not available.")
    if ebitda <= 0:
        return _m(key, label, "x", None, "bad", "Carries net debt while EBITDA is zero or negative.")
    r = nd / ebitda
    status = "good" if r < 2 else "warn" if r < 4 else "bad"
    return _m(key, label, "x", r, status, f"Net debt is {r:.1f} times trailing EBITDA.")


def interest_coverage(st: Statements) -> HealthMetric:
    key, label = "interest_coverage", "Interest coverage"
    ebit = _ttm_or_annual(st, "ebit")
    interest = _ttm_or_annual(st, "interest_expense")
    if interest is None:
        debt = _latest_bs(st, "total_debt")
        if debt == 0:
            return _m(key, label, "x", None, "good", "No debt and no interest expense.")
        return _na(key, label, "x", "Interest expense is not available.")
    interest = abs(interest)
    if interest == 0:
        return _m(key, label, "x", None, "good", "No interest expense.")
    if ebit is None:
        return _na(key, label, "x", "EBIT is not available.")
    r = ebit / interest
    if ebit <= 0:
        return _m(key, label, "x", r, "bad", "Operating result is negative, so it does not cover interest.")
    status = "good" if r > 5 else "warn" if r > 2 else "bad"
    return _m(key, label, "x", r, status, f"Operating profit covers interest {r:.1f} times.")


def altman_z(st: Statements, market_cap: Optional[float], currency_mismatch: bool = False) -> HealthMetric:
    key, label = "altman_z", "Altman Z-score"
    note = " Designed for manufacturers; less meaningful for financials."
    U = "ratio"  # distinct from Piotroski's "score"
    if currency_mismatch:
        return _na(key, label, U, "Currency mismatch: market cap could not be converted to the reporting currency." + note)
    fr = st.annual
    cols = fr.periods()
    if not cols:
        return _na(key, label, U, "Annual statements are not available." + note)
    c = cols[-1]
    ta, tl = val(fr, "total_assets", c), val(fr, "total_liabilities", c)
    wc, re_ = val(fr, "working_capital", c), val(fr, "retained_earnings", c)
    ebit, sales = val(fr, "ebit", c), val(fr, "revenue", c)
    missing = [n for n, v in (("total assets", ta), ("total liabilities", tl), ("working capital", wc),
                              ("retained earnings", re_), ("EBIT", ebit), ("sales", sales),
                              ("market cap", market_cap)) if v is None]
    if missing:
        return _na(key, label, U, f"Missing: {', '.join(missing)}." + note)
    if not ta or not tl:
        return _na(key, label, U, "Total assets or liabilities are zero." + note)
    z = (1.2 * wc / ta + 1.4 * re_ / ta + 3.3 * ebit / ta + 0.6 * market_cap / tl + 1.0 * sales / ta)
    status = "good" if z > 2.99 else "warn" if z >= 1.81 else "bad"
    zone = {"good": "safe", "warn": "grey", "bad": "distress"}[status]
    return _m(key, label, U, z, status, f"Z-score of {z:.2f} falls in the {zone} zone." + note)


def piotroski_f(st: Statements) -> HealthMetric:
    key, label = "piotroski_f", "Piotroski F-score"
    fr = st.annual
    cols = fr.periods()
    if len(cols) < 2:
        return _na(key, label, "score", "Two annual statements are required.")
    c1, c0 = cols[-1], cols[-2]

    def g(name, c):
        return val(fr, name, c)

    def ratio(a, b):
        return None if a is None or b in (None, 0) else a / b

    prev = {cols[i]: cols[i - 1] for i in range(1, len(cols))}  # period -> prior period

    def open_assets(c):  # total assets at the start of the year = prior period end
        return g("total_assets", prev[c]) if c in prev else None

    def roa(c): return ratio(g("net_income", c), open_assets(c))
    def lev(c): return ratio(g("long_term_debt", c), g("total_assets", c))
    def cur(c): return ratio(g("current_assets", c), g("current_liabilities", c))
    def gm(c): return ratio(g("gross_profit", c), g("revenue", c))
    def at(c): return ratio(g("revenue", c), open_assets(c))

    def cmp(f, op):
        a, b = f(c1), f(c0)
        return None if a is None or b is None else op(a, b)

    ocf1, ni1 = g("operating_cash_flow", c1), g("net_income", c1)
    sh1, sh0 = g("shares", c1), g("shares", c0)
    r1 = roa(c1)
    tests = [
        None if r1 is None else r1 > 0,
        None if ocf1 is None else ocf1 > 0,
        cmp(roa, lambda a, b: a > b),
        None if ocf1 is None or ni1 is None else ocf1 > ni1,
        cmp(lev, lambda a, b: a < b),
        cmp(cur, lambda a, b: a > b),
        None if sh1 is None or sh0 is None else sh1 <= sh0,
        cmp(gm, lambda a, b: a > b),
        cmp(at, lambda a, b: a > b),
    ]
    avail = [t for t in tests if t is not None]
    if not avail:
        return _na(key, label, "score", "Statement data needed for the tests is not available.")
    score = sum(1 for t in avail if t)
    if len(avail) < 7:
        return _m(key, label, "score", float(score), "na",
                  f"Passes {score} of {len(avail)} tests; only {len(avail)} of 9 tests available.")
    status = "good" if score >= 7 else "warn" if score >= 4 else "bad"
    return _m(key, label, "score", float(score), status,
              f"Passes {score} of {len(avail)} tests"
              + (" (some inputs missing)." if len(avail) < 9 else "."))


def compute_health(st: Statements, market_cap: Optional[float],
                   currency_mismatch: bool = False) -> List[HealthMetric]:
    return [cash_runway(st), dilution_yoy(st), net_debt_to_ebitda(st), interest_coverage(st),
            altman_z(st, market_cap, currency_mismatch), piotroski_f(st)]


def latest_period_end(st: Statements) -> Optional[date]:
    cols = st.quarterly.periods() + st.annual.periods()
    return pd.Timestamp(max(cols)).date() if cols else None

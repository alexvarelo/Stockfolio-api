"""Fetching layer for fundamentals: yfinance statements/info behind TTL caches, then pure maths."""
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

import pandas as pd
import yfinance as yf

from app.core import cache as cache_layer
from app.core.exceptions import TickerNotFoundError
from app.models.analysis import (
    CompareGrowth, CompareHealth, CompareMargins, CompareResponse, CompareReturns, CompareRow,
    CompareValuation, FinancialsResponse, HealthResponse,
)
from app.services import fundamentals as fm
from app.services.portfolio_risk_service import PENCE, _fetch_fx, infer_currency

logger = logging.getLogger(__name__)

N_ITEMS = {"annual": 5, "quarterly": 8}


def _frame(getter) -> pd.DataFrame:
    try:
        df = getter()
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()
    except Exception as e:
        logger.warning(f"Statement fetch failed: {e}")
        return pd.DataFrame()


def get_info(ticker: str) -> Dict[str, Any]:
    """yfinance `info` dict (price cache TTL); {} when unavailable."""
    t = ticker.upper()

    def load():
        try:
            info = yf.Ticker(t).info
        except Exception as e:
            logger.warning(f"No info for {t}: {e}")
            return None
        return info or None

    return cache_layer.price_cache.get_or_set(f"info_{t}", load) or {}


def get_statements(ticker: str, info: Optional[Dict[str, Any]] = None) -> fm.Statements:
    """Annual + quarterly statements, cached 24 h. Raises TickerNotFoundError if nothing came back."""
    t = ticker.upper()

    def load():
        tk = yf.Ticker(t)
        st = fm.Statements(
            annual=fm.Frames(_frame(lambda: tk.get_income_stmt(freq="yearly", pretty=True)),
                             _frame(lambda: tk.get_balance_sheet(freq="yearly", pretty=True)),
                             _frame(lambda: tk.get_cash_flow(freq="yearly", pretty=True))),
            quarterly=fm.Frames(_frame(lambda: tk.get_income_stmt(freq="quarterly", pretty=True)),
                                _frame(lambda: tk.get_balance_sheet(freq="quarterly", pretty=True)),
                                _frame(lambda: tk.get_cash_flow(freq="quarterly", pretty=True))),
        )
        if st.is_empty():
            raise TickerNotFoundError(t)
        st.financial_currency = (get_info(t) if info is None else info).get("financialCurrency")
        return st

    return cache_layer.financials_cache.get_or_set(f"statements_{t}", load)


def get_financials(ticker: str, period: str) -> FinancialsResponse:
    t = ticker.upper()
    st = get_statements(t)
    fr = st.annual if period == "annual" else st.quarterly
    return FinancialsResponse(ticker=t, currency=st.financial_currency, period=period,
                              items=fm.build_items(fr, N_ITEMS[period]))


def get_health(ticker: str) -> HealthResponse:
    from datetime import date
    t = ticker.upper()
    st = get_statements(t)
    market_cap = get_info(t).get("marketCap")
    return HealthResponse(ticker=t, as_of=fm.latest_period_end(st) or date.today(),
                          metrics=fm.compute_health(st, fm._num(market_cap)))


# ---------------------------------------------------------------- compare

def _price_return(closes: Optional[pd.Series], years: int) -> Optional[float]:
    if closes is None or closes.empty:
        return None
    last_ts = closes.index[-1]
    target = last_ts - pd.DateOffset(years=years)
    if closes.index[0] > target + pd.Timedelta(days=7):
        return None  # history shorter than the window
    base = closes.loc[:target]
    start = float(base.iloc[-1]) if not base.empty else float(closes.iloc[0])
    return None if start <= 0 else float(closes.iloc[-1]) / start - 1


def _load_row(ticker: str, service) -> Optional[Dict[str, Any]]:
    info = get_info(ticker)
    try:
        closes = service.get_daily_closes(ticker, "5y")
        if closes is not None:
            closes = closes.dropna()
            if closes.index.tz is not None:
                closes.index = closes.index.tz_localize(None)
    except Exception as e:
        logger.warning(f"No history for {ticker}: {e}")
        closes = None
    if closes is not None and closes.empty:
        closes = None
    has_price = fm._num(info.get("currentPrice")) is not None or fm._num(info.get("regularMarketPrice")) is not None
    if closes is None and not has_price:
        return None
    try:
        st = get_statements(ticker, info)
    except Exception:
        st = None
    currency = info.get("currency") or infer_currency(ticker, service)
    return {"ticker": ticker, "info": info, "closes": closes, "st": st, "currency": currency}


def compute_compare(tickers: List[str], service) -> CompareResponse:
    base = "USD"
    with ThreadPoolExecutor(max_workers=6) as ex:
        loaded = list(ex.map(lambda t: _load_row(t, service), tickers))

    fx_cache: Dict[str, Optional[float]] = {}

    def to_usd_rate(cur: Optional[str]) -> Optional[float]:
        if not cur:
            return None
        code = "GBP" if cur in PENCE else cur
        if code == base:
            return 1.0
        if code not in fx_cache:
            s = _fetch_fx(service, code, base, "5d")
            fx_cache[code] = float(s.dropna().iloc[-1]) if s is not None and not s.dropna().empty else None
        return fx_cache[code]

    rows: List[CompareRow] = []
    missing: List[str] = []
    for t, d in zip(tickers, loaded):
        if d is None:
            missing.append(t)
            continue
        info, closes, st, cur = d["info"], d["closes"], d["st"], d["currency"]
        num = lambda k: fm._num(info.get(k))  # noqa: E731
        price = num("currentPrice") or num("regularMarketPrice")
        if price is None and closes is not None:
            price = float(closes.iloc[-1])
        mcap = num("marketCap")
        rate = to_usd_rate(cur) if mcap is not None else None
        hm: Dict[str, Optional[float]] = {}
        if st is not None:
            hm = {m.key: m.value for m in fm.compute_health(st, mcap)}
        cr = num("currentRatio")
        if cr is None and st is not None:
            ca, cl = fm._latest_bs(st, "current_assets"), fm._latest_bs(st, "current_liabilities")
            cr = ca / cl if ca is not None and cl else None
        rows.append(CompareRow(
            ticker=t, name=info.get("shortName") or info.get("longName"), currency=cur, price=price,
            market_cap=mcap, market_cap_usd=mcap * rate if mcap is not None and rate is not None else None,
            valuation=CompareValuation(
                pe=num("trailingPE"), forward_pe=num("forwardPE"),
                peg=num("trailingPegRatio") if num("trailingPegRatio") is not None else num("pegRatio"),
                ev_ebitda=num("enterpriseToEbitda"), price_to_sales=num("priceToSalesTrailing12Months"),
                price_to_book=num("priceToBook")),
            growth=CompareGrowth(revenue_growth_yoy=num("revenueGrowth"), earnings_growth_yoy=num("earningsGrowth")),
            margins=CompareMargins(gross=num("grossMargins"), operating=num("operatingMargins"),
                                   net=num("profitMargins")),
            health=CompareHealth(net_debt_to_ebitda=hm.get("net_debt_to_ebitda"), current_ratio=cr,
                                 altman_z=hm.get("altman_z")),
            returns=CompareReturns(r1y=_price_return(closes, 1), r3y=_price_return(closes, 3),
                                   r5y=_price_return(closes, 5)),
        ))
    return CompareResponse(tickers=tickers, base_currency=base, rows=rows, missing=missing)

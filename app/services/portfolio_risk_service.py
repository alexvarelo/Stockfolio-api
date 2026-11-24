"""Orchestrates data fetching (via the yfinance service) and risk.py calculations."""
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple

import pandas as pd

from app.models.schemas import (
    PortfolioRiskRequest, PortfolioRiskResponse, PortfolioWeight,
    LargestPosition, CorrelationMatrix, ExcludedTicker,
)
from app.services import risk

logger = logging.getLogger(__name__)

PENCE = {"GBp", "GBX"}

SUFFIX_CURRENCY = {
    "MC": "EUR", "DE": "EUR", "PA": "EUR", "AS": "EUR", "MI": "EUR", "BR": "EUR",
    "LS": "EUR", "HE": "EUR", "VI": "EUR", "F": "EUR",
    "L": "GBp", "SW": "CHF", "TO": "CAD", "AX": "AUD", "T": "JPY", "HK": "HKD",
    "ST": "SEK", "CO": "DKK", "OL": "NOK",
}


def infer_currency(ticker: str, service) -> Optional[str]:
    """yfinance's quote currency first (a .L ETF may trade in USD), then the exchange
    suffix; no-suffix tickers default to USD. None if unknown."""
    t = ticker.upper()
    try:
        cur = service.get_currency(ticker)
    except Exception:
        cur = None
    if cur:
        return cur
    if "." in t:
        suffix = t.rsplit(".", 1)[1]
        if suffix in SUFFIX_CURRENCY:
            return SUFFIX_CURRENCY[suffix]
        return None
    return "USD"


def _fetch_fx(service, local: str, base: str, period: str) -> Optional[pd.Series]:
    """Base-per-local FX series, e.g. EURUSD=X for EUR assets in USD."""
    try:
        return risk.normalize_index(service.get_daily_closes(f"{local}{base}=X", period))
    except Exception:
        pass
    try:  # fall back to the inverse pair
        inv = risk.normalize_index(service.get_daily_closes(f"{base}{local}=X", period))
        return 1.0 / inv
    except Exception:
        return None


def compute_portfolio_risk(req: PortfolioRiskRequest, service) -> PortfolioRiskResponse:
    from fastapi import HTTPException

    base = req.base_currency.upper()
    quantities: Dict[str, float] = {}
    for p in req.positions:
        t = p.ticker.strip().upper()
        quantities[t] = quantities.get(t, 0.0) + p.quantity

    def load(t: str) -> Tuple[str, Optional[pd.Series], Optional[str]]:
        try:
            closes = risk.normalize_index(service.get_daily_closes(t, req.period))
            if closes.empty:
                return t, None, None
            return t, closes, infer_currency(t, service)
        except Exception as e:
            logger.warning(f"No data for {t}: {e}")
            return t, None, None

    with ThreadPoolExecutor(max_workers=8) as ex:
        loaded = list(ex.map(load, quantities))

    local: Dict[str, pd.Series] = {}
    currency: Dict[str, str] = {}
    excluded: Dict[str, str] = {}
    for t, closes, cur in loaded:
        if closes is None:
            excluded[t] = "no_history"
        elif cur is None:
            logger.warning(f"Unknown currency for {t}; excluding")
            excluded[t] = "unknown_currency"
        else:
            local[t] = closes
            currency[t] = cur

    if not local:
        raise HTTPException(status_code=422, detail="No price data available for any position")

    # Benchmark (fetched raw; converted to base below)
    bench_raw = None
    bench_cur: Optional[str] = None
    try:
        bench_raw = risk.normalize_index(service.get_daily_closes(req.benchmark, req.period))
        bench_cur = infer_currency(req.benchmark, service)
        if bench_cur is None:
            logger.warning(f"Unknown benchmark currency for {req.benchmark}; beta disabled")
            bench_raw = None
    except Exception as e:
        logger.warning(f"No benchmark data for {req.benchmark}: {e}")

    def code(c: str) -> str:
        return "GBP" if c in PENCE else c

    # FX series, one per distinct non-base currency
    needed = {code(c) for c in currency.values()}
    if bench_cur:
        needed.add(code(bench_cur))
    fx: Dict[str, Optional[pd.Series]] = {
        cur: _fetch_fx(service, cur, base, req.period) for cur in needed if cur != base}

    converted: Dict[str, pd.Series] = {}
    for t, closes in local.items():
        cur = currency[t]
        rate = None
        if code(cur) != base:
            rate = fx.get(code(cur))
            if rate is None:
                logger.warning(f"No FX rate {code(cur)}->{base}; excluding {t}")
                excluded[t] = "no_fx"
                continue
        converted[t] = risk.to_base_currency(closes, rate, cur in PENCE)

    if not converted:
        raise HTTPException(status_code=422, detail="No price data available for any position")

    bench = None
    if bench_raw is not None:
        if code(bench_cur) != base and fx.get(code(bench_cur)) is None:
            logger.warning(f"No FX rate for benchmark {req.benchmark}; beta disabled")
            bench_cur = None
        else:
            bench = risk.to_base_currency(bench_raw, fx.get(code(bench_cur)) if code(bench_cur) != base else None,
                                          bench_cur in PENCE)

    union_series = dict(converted)
    if bench is not None:
        union_series["__bench__"] = bench
    aligned = risk.align_prices(union_series)
    if aligned.empty:
        raise HTTPException(status_code=422, detail="No overlapping trading dates between positions")
    bench_aligned = aligned.pop("__bench__") if bench is not None else None
    prices = aligned[list(converted)]

    kept_q = {t: quantities[t] for t in converted}
    res = risk.compute_risk(prices, kept_q, bench_aligned, req.risk_free_rate)
    valuation_date = res["as_of"]
    last_ts = prices.index[-1]

    weights = []
    for t in converted:
        base_price = float(prices[t].iloc[-1])
        # local quoted price at the valuation date (last close on or before it)
        local_price = float(local[t].loc[:last_ts].iloc[-1])
        weights.append(PortfolioWeight(
            ticker=t, quantity=kept_q[t], price=local_price,
            currency=currency[t], fx_rate=base_price / local_price,
            value_base=res["position_values"][t], weight=res["weights"][t],
        ))

    excluded_list: List[ExcludedTicker] = [
        ExcludedTicker(ticker=t, reason=r) for t, r in sorted(excluded.items())]

    return PortfolioRiskResponse(
        as_of=valuation_date, valuation_date=valuation_date, period=req.period,
        benchmark=req.benchmark, benchmark_currency=bench_cur if bench is not None else None,
        base_currency=base, total_value=res["total_value"], weights=weights,
        beta=res["beta"], volatility_annual=res["volatility_annual"],
        annual_return=res["annual_return"], max_drawdown=res["max_drawdown"],
        sharpe_ratio=res["sharpe_ratio"],
        largest_position=LargestPosition(**res["largest_position"]),
        hhi=res["hhi"], effective_positions=res["effective_positions"],
        correlation=CorrelationMatrix(**res["correlation"]),
        missing_tickers=[e.ticker for e in excluded_list], excluded=excluded_list,
        observations=res["observations"],
    )

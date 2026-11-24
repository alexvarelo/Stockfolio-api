"""Orchestrates data fetching (via the yfinance service) and risk.py calculations."""
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional, Tuple

import pandas as pd

from app.models.schemas import (
    PortfolioRiskRequest, PortfolioRiskResponse, PortfolioWeight,
    LargestPosition, CorrelationMatrix,
)
from app.services import risk

logger = logging.getLogger(__name__)

PENCE = {"GBp", "GBX"}


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
            return t, closes, service.get_currency(t)
        except Exception as e:
            logger.warning(f"No data for {t}: {e}")
            return t, None, None

    with ThreadPoolExecutor(max_workers=8) as ex:
        loaded = list(ex.map(load, quantities))

    local: Dict[str, pd.Series] = {}
    currency: Dict[str, str] = {}
    missing = []
    for t, closes, cur in loaded:
        if closes is None:
            missing.append(t)
        else:
            local[t] = closes
            currency[t] = cur or base

    if not local:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="No price data available for any position")

    # FX series, one per distinct non-base currency
    fx: Dict[str, Optional[pd.Series]] = {}
    for cur in {("GBP" if c in PENCE else c) for c in currency.values()}:
        if cur != base:
            fx[cur] = _fetch_fx(service, cur, base, req.period)

    converted: Dict[str, pd.Series] = {}
    for t, closes in local.items():
        cur = currency[t]
        pence = cur in PENCE
        cur_code = "GBP" if pence else cur
        rate = None
        if cur_code != base:
            rate = fx.get(cur_code)
            if rate is None:
                logger.warning(f"No FX rate {cur_code}->{base}; excluding {t}")
                missing.append(t)
                continue
        converted[t] = risk.to_base_currency(closes, rate, pence)

    if not converted:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="No price data available for any position")

    bench = None
    try:
        bench = risk.normalize_index(service.get_daily_closes(req.benchmark, req.period))
    except Exception as e:
        logger.warning(f"No benchmark data for {req.benchmark}: {e}")

    union_series = dict(converted)
    if bench is not None:
        union_series["__bench__"] = bench
    aligned = risk.align_prices(union_series)
    if aligned.empty:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="No overlapping trading dates between positions")
    bench_aligned = aligned.pop("__bench__") if bench is not None else None
    prices = aligned[list(converted)]

    kept_q = {t: quantities[t] for t in converted}
    res = risk.compute_risk(prices, kept_q, bench_aligned, req.risk_free_rate)

    weights = []
    for t in converted:
        weights.append(PortfolioWeight(
            ticker=t, quantity=kept_q[t], price=float(local[t].iloc[-1]),
            currency=currency[t], value_base=res["position_values"][t],
            weight=res["weights"][t],
        ))

    return PortfolioRiskResponse(
        as_of=res["as_of"], period=req.period, benchmark=req.benchmark,
        base_currency=base, total_value=res["total_value"], weights=weights,
        beta=res["beta"], volatility_annual=res["volatility_annual"],
        annual_return=res["annual_return"], max_drawdown=res["max_drawdown"],
        sharpe_ratio=res["sharpe_ratio"],
        largest_position=LargestPosition(**res["largest_position"]),
        hhi=res["hhi"], effective_positions=res["effective_positions"],
        correlation=CorrelationMatrix(**res["correlation"]),
        missing_tickers=sorted(set(missing)), observations=res["observations"],
    )

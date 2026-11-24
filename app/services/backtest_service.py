"""Fetches prices (cached via the yfinance service), converts to base currency and runs the backtest engine."""
import logging
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Dict

import numpy as np
import pandas as pd
from fastapi import HTTPException

from app.models.strategies import BacktestRequest, BacktestResponse
from app.services import risk, backtest
from app.services.portfolio_risk_service import PENCE, infer_currency, _fetch_fx

logger = logging.getLogger(__name__)

HISTORY_PERIOD = "max"       # full history: gives indicator warm-up before start_date
START_TOLERANCE_DAYS = 10    # first common price date may trail start_date by this much
MIN_WARMUP_WINDOW = 140      # trading days of indicator history even for short windows


def warmup_days(slow: int) -> int:
    """Calendar days of pre-start history kept for indicators: ceil(max(slow, 140) x 1.5)."""
    return math.ceil(max(slow, MIN_WARMUP_WINDOW) * 1.5)


def run_strategy_backtest(req: BacktestRequest, service) -> BacktestResponse:
    base = req.base_currency
    weights = backtest.normalize_weights({t.ticker: t.weight for t in req.tickers})

    def load(t: str):
        try:
            closes = risk.normalize_index(service.get_daily_closes(t, HISTORY_PERIOD))
        except Exception as e:
            logger.warning(f"No data for {t}: {e}")
            return t, None, None
        if closes.empty:
            return t, None, None
        return t, closes, infer_currency(t, service)

    with ThreadPoolExecutor(max_workers=8) as ex:
        loaded = list(ex.map(load, weights))

    def code(c: str) -> str:
        return "GBP" if c in PENCE else c

    local: Dict[str, pd.Series] = {}
    currency: Dict[str, str] = {}
    for t, closes, cur in loaded:
        if closes is None:
            raise HTTPException(422, f"No price history available for {t}")
        if cur is None:
            raise HTTPException(422, f"Could not determine the currency of {t}")
        local[t], currency[t] = closes, cur

    start = pd.Timestamp(req.start_date)
    for t, closes in local.items():
        if (closes.index[closes.index >= start][:1].size == 0
                or (closes.index[closes.index >= start][0] - start).days > START_TOLERANCE_DAYS):
            raise HTTPException(
                422, f"{t} has no price data at start_date {req.start_date} (history starts {closes.index[0].date()})")

    fx = {c: _fetch_fx(service, c, base, HISTORY_PERIOD)
          for c in {code(c) for c in currency.values()} if c != base}
    for c, rate in fx.items():
        if rate is None or len(rate) == 0:
            continue  # reported per ticker below
        r = risk.normalize_index(rate)
        after = r.index[r.index >= start]
        if after.size == 0 or (after[0] - start).days > START_TOLERANCE_DAYS:
            raise HTTPException(
                422, f"FX series {c}->{base} does not cover start_date {req.start_date} "
                     f"(FX history starts {r.index[0].date()}); choose a later start_date or another base_currency")
    converted: Dict[str, pd.Series] = {}
    for t, closes in local.items():
        cur = currency[t]
        rate = None
        if code(cur) != base:
            rate = fx.get(code(cur))
            if rate is None:
                raise HTTPException(422, f"No FX rate {code(cur)}->{base} available for {t}")
        conv = risk.to_base_currency(closes, rate, cur in PENCE)
        converted[t] = conv[np.isfinite(conv) & (conv > 0)]  # drop non-positive prices

    for t, s in converted.items():
        sw = s[s.index >= start]
        if sw.empty or (sw.index[0] - start).days > START_TOLERANCE_DAYS:
            first = s.index[0].date() if len(s) else None
            raise HTTPException(
                422, f"{t} has no price data at start_date {req.start_date} (history starts {first})")

    prices = risk.align_prices(converted)
    prices = prices[prices.index >= start - timedelta(days=warmup_days(req.params.slow))]
    signal_prices = None
    if req.strategy in ("rsi", "ma_cross"):
        t0 = prices.columns[0]
        signal_prices = local[t0].reindex(prices.index).ffill(limit=risk.FFILL_LIMIT)
    p = req.params
    try:
        res = backtest.run_backtest(
            prices, req.strategy, weights, req.start_date, req.end_date, req.initial_capital,
            monthly_amount=p.monthly_amount, rebalance_frequency=p.rebalance_frequency,
            rsi_buy=p.rsi_buy, rsi_sell=p.rsi_sell, fast=p.fast, slow=p.slow, fee_bps=req.fee_bps,
            signal_prices=signal_prices)
    except ValueError as e:
        raise HTTPException(422, str(e))

    for key in ("sim", "bench"):
        if not (np.isfinite(res[key]["values"]).all() and np.isfinite(res[key]["invested"]).all()):
            raise HTTPException(422, "Non-finite values in backtest results; check amounts and price data")

    notes = ["Past performance does not predict future results.",
             "Trades execute at the daily close in base currency; cash earns 0."]
    if req.strategy in ("rsi", "ma_cross"):
        notes.append("Signals are computed on day t close and executed on day t+1 close (no look-ahead). "
                     "Indicators use local-currency closes; trades are executed in base currency. "
                     "The strategy starts in cash and only enters after a crossing signal.")
    if req.fee_bps:
        notes.append(f"A fee of {req.fee_bps:g} bps is applied to each trade's notional.")
    if req.strategy == "dca":
        notes.append("Benchmark is a lump sum: the initial capital plus every scheduled contribution invested "
                     "on day one at the same weights (same fees), then held.")
    else:
        notes.append("Benchmark is buy-and-hold of the same tickers and weights with the same cash flows.")

    return BacktestResponse(
        strategy=req.strategy, base_currency=base,
        start_date=res["start_date"], end_date=res["end_date"],
        equity_curve=res["equity_curve"], metrics=res["metrics"],
        trades=res["trades"], notes=notes)

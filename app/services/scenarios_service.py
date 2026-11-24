"""Fetching/orchestration for /scenarios: reuses the Phase 1 currency + alignment helpers."""
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from fastapi import HTTPException

from app.models.scenarios import (
    ScenarioExcluded, StressRequest, StressResponse, StressScenario, StressPosition,
    MonteCarloRequest, MonteCarloResponse, WhatIfRequest, WhatIfResponse, WhatIfDelta, RiskSnapshot,
    MonteCarloSummary,
)
from app.services import risk, scenarios as sc
from app.services.portfolio_risk_service import PENCE, _fetch_fx, fx_code, infer_currency

logger = logging.getLogger(__name__)

BENCHMARK = "^GSPC"
MIN_OBS = 60
SHORT_HISTORY_RATIO = 0.5


def merge_positions(positions) -> Dict[str, float]:
    q: Dict[str, float] = {}
    for p in positions:
        t = p.ticker.strip().upper()
        q[t] = q.get(t, 0.0) + p.quantity
    return q


def load_base_series(symbols: List[str], base: str, period: str, service
                     ) -> Tuple[Dict[str, pd.Series], Dict[str, str]]:
    """Daily closes of each symbol converted to `base` (FX + pence handled as in Phase 1).
    Returns (series, excluded reasons)."""
    def load(t):
        try:
            closes = risk.normalize_index(service.get_daily_closes(t, period))
            if closes.empty:
                return t, None, None
            return t, closes, infer_currency(t, service)
        except Exception as e:
            logger.warning(f"No data for {t}: {e}")
            return t, None, None

    with ThreadPoolExecutor(max_workers=8) as ex:
        loaded = list(ex.map(load, symbols))
    local, cur_of, excluded = {}, {}, {}
    for t, closes, cur in loaded:
        if closes is None:
            excluded[t] = "no_history"
        elif cur is None:
            excluded[t] = "unknown_currency"
        else:
            local[t], cur_of[t] = closes, cur
    needed = {fx_code(c) for c in cur_of.values()} - {base}
    fx = {c: _fetch_fx(service, c, base, period) for c in needed}
    out = {}
    for t, closes in local.items():
        cur = cur_of[t]
        rate = None
        if fx_code(cur) != base:
            rate = fx.get(fx_code(cur))
            if rate is None:
                excluded[t] = "no_fx"
                continue
        out[t] = risk.to_base_currency(closes, rate, cur in PENCE)
    return out, excluded


def _excl(d: Dict[str, str]) -> List[ScenarioExcluded]:
    return [ScenarioExcluded(ticker=t, reason=r) for t, r in sorted(d.items())]


# ---------------- stress ----------------
def compute_stress(req: StressRequest, service) -> StressResponse:
    """Stress test the current portfolio.

    Historical windows: a position's own total return in base currency (FX move included,
    since prices are converted day by day) if its data covers >= 90% of the window; otherwise
    beta_proxy = clamp(beta, 0, 3) x S&P 500 return (beta vs ^GSPC in base currency over the
    last 2y, default 1). Proxies use the benchmark in base currency, i.e. the position's own
    FX move is ignored. Shocks: beta x shock (a plain market move, FX ignored)."""
    base = req.base_currency
    quantities = merge_positions(req.positions)
    series, excluded = load_base_series(list(quantities) + [BENCHMARK], base, "max", service)
    bench = series.pop(BENCHMARK, None)
    excluded.pop(BENCHMARK, None)
    series = {t: s for t, s in series.items() if t in quantities}
    if not series:
        raise HTTPException(status_code=422, detail="No price data available for any position")
    if bench is None:
        raise HTTPException(status_code=422, detail="No benchmark data available")

    values = {t: quantities[t] * float(s.iloc[-1]) for t, s in series.items()}
    total = sum(values.values())
    weights = {t: v / total for t, v in values.items()}

    cutoff = bench.index[-1] - pd.Timedelta(days=730)
    betas = {}
    for t, s in series.items():
        try:
            res = risk.compute_risk(s.loc[cutoff:].to_frame(t), {t: 1.0}, bench.loc[cutoff:])
            betas[t] = sc.clamp_beta(res["beta"])
        except Exception:
            betas[t] = 1.0

    def build(key, label, start, end, bench_ret, hist: bool, shock=None) -> StressScenario:
        positions = []
        for t, s in series.items():
            r = sc.window_return(s, start, end) if hist else None
            if r is not None:
                positions.append(StressPosition(ticker=t, ret=r, method="historical", weight=weights[t]))
            else:
                method = "beta_proxy" if hist else "shock"
                positions.append(StressPosition(ticker=t, ret=max(-1.0, betas[t] * bench_ret), method=method,
                                                weight=weights[t]))
        pr = sum(p.weight * p.ret for p in positions)
        methods = {p.method for p in positions}
        method = "shock" if not hist else ("beta_proxy" if "beta_proxy" in methods else "historical")
        return StressScenario(
            key=key, label=label, period_start=start, period_end=end, method=method,
            portfolio_return=pr, value_after=total * (1 + pr), pnl=total * pr,
            positions=positions, benchmark_return=bench_ret)

    scenarios = []
    for key, label, start, end in sc.HISTORICAL_WINDOWS:
        b = sc.window_return(bench, start, end)
        if b is None:
            logger.warning(f"Benchmark lacks data for {key}")
            continue
        scenarios.append(build(key, label, start, end, b, True))
    for s in req.shocks:
        pct = round(s * 100, 2)
        key = f"shock_{pct:g}"
        sc_ = build(key, f"Market shock {pct:+g}%", None, None, s, False)
        scenarios.append(sc_)
    return StressResponse(base_currency=base, current_value=round(total, 2), scenarios=scenarios,
                          excluded=_excl(excluded))


# ---------------- Monte Carlo ----------------
def _prepare_market(tickers: List[str], base: str, lookback: str, service, required: List[str]):
    """Aligned base-currency prices of `tickers` + benchmark (or None) + excluded + obs."""
    series, excluded = load_base_series(list(tickers) + [BENCHMARK], base, lookback, service)
    bench = series.pop(BENCHMARK, None)
    excluded.pop(BENCHMARK, None)
    series = {t: s for t, s in series.items() if t in tickers}
    if series:
        longest = max(len(s) for s in series.values())
        for t in [t for t, s in series.items() if len(s) < SHORT_HISTORY_RATIO * longest]:
            excluded[t] = "short_history"
            del series[t]
    missing = [t for t in required if t not in series]
    if missing:
        raise HTTPException(status_code=422,
                            detail=f"No usable price data for: {', '.join(missing)} ({excluded.get(missing[0])})")
    if not series:
        raise HTTPException(status_code=422, detail="No price data available for any position")
    prices = risk.align_prices(series)
    if len(prices) < MIN_OBS:
        raise HTTPException(status_code=422, detail="Not enough overlapping price history")
    return prices, bench, excluded


def _lookback_label(requested: str, obs: int) -> str:
    years = obs / sc.TRADING_DAYS
    return requested if years >= 0.9 * int(requested[:-1]) else f"{years:.1f}y"


def _start_values(prices: pd.DataFrame, quantities: Dict[str, float]) -> np.ndarray:
    last = prices.iloc[-1]
    return np.array([quantities.get(t, 0.0) * float(last[t]) for t in prices.columns])


def compute_montecarlo(req: MonteCarloRequest, service) -> MonteCarloResponse:
    base = req.base_currency
    q = merge_positions(req.positions)
    prices, _, excluded = _prepare_market(list(q), base, req.lookback, service, [])
    kept = {t: q[t] for t in prices.columns}
    rets = prices.pct_change().dropna().to_numpy()
    seed = sc.DEFAULT_SEED if req.seed is None else req.seed
    days = req.horizon_years * sc.TRADING_DAYS
    idx = sc.bootstrap_indices(len(rets), req.paths, days, seed)
    v0 = _start_values(prices, kept)
    sim = sc.simulate(rets, v0, idx, req.monthly_contribution)
    contrib = req.monthly_contribution * sc.n_contributions(days)
    summ = sc.summarize(sim, float(v0.sum()), contrib)
    return MonteCarloResponse(
        base_currency=base, horizon_years=req.horizon_years, paths=req.paths, seed=seed,
        lookback_used=_lookback_label(req.lookback, len(rets)), observations=len(rets),
        excluded=_excl(excluded), **summ)


def apply_changes(held: Dict[str, float], changes) -> Dict[str, float]:
    new = dict(held)
    for s in changes.sell:
        t = s.ticker.strip().upper()
        if t not in new or s.quantity > new[t] + 1e-9:
            raise HTTPException(status_code=422, detail=f"Cannot sell {s.quantity} of {t}: held {new.get(t, 0)}")
        new[t] -= s.quantity
    for b in changes.buy:
        t = b.ticker.strip().upper()
        new[t] = new.get(t, 0.0) + b.quantity
    new = {t: v for t, v in new.items() if v > 1e-9}
    if not new:
        raise HTTPException(status_code=422, detail="Modified portfolio is empty")
    return new


def _risk_snapshot(prices: pd.DataFrame, bench: Optional[pd.Series], q: Dict[str, float]) -> RiskSnapshot:
    cols = [t for t in prices.columns if q.get(t, 0) > 0]
    res = risk.compute_risk(prices[cols], {t: q[t] for t in cols}, bench)
    return RiskSnapshot(volatility_annual=res["volatility_annual"], beta=res["beta"],
                        max_drawdown=res["max_drawdown"], hhi=res["hhi"])


def compute_whatif(req: WhatIfRequest, service) -> WhatIfResponse:
    cur = req.current
    base = cur.base_currency
    q0 = merge_positions(cur.positions)
    q1 = apply_changes(q0, req.changes)  # validates sells first (422) before any fetch
    union = sorted(set(q0) | set(q1))
    prices, bench, excluded = _prepare_market(union, base, cur.lookback, service, sorted(set(q1)))
    q0k = {t: v for t, v in q0.items() if t in prices.columns}
    if not q0k:
        raise HTTPException(status_code=422, detail="No price data available for the current positions")
    rets = prices.pct_change().dropna().to_numpy()
    seed = sc.DEFAULT_SEED if cur.seed is None else cur.seed
    days = cur.horizon_years * sc.TRADING_DAYS
    idx = sc.bootstrap_indices(len(rets), cur.paths, days, seed)  # shared => paired comparison
    c0 = cur.monthly_contribution
    c1 = c0 if req.changes.monthly_contribution is None else req.changes.monthly_contribution
    n_c = sc.n_contributions(days)

    def run(q, c) -> dict:
        v0 = _start_values(prices, q)
        return sc.summarize(sc.simulate(rets, v0, idx, c), float(v0.sum()), c * n_c)

    s0, s1 = run(q0k, c0), run(q1, c1)
    bench_s = bench
    return WhatIfResponse(
        base_currency=base, horizon_years=cur.horizon_years, paths=cur.paths, seed=seed,
        lookback_used=_lookback_label(cur.lookback, len(rets)), observations=len(rets),
        current=MonteCarloSummary(**s0), modified=MonteCarloSummary(**s1),
        delta=WhatIfDelta(p50=round(s1["final"]["p50"] - s0["final"]["p50"], 2),
                          p5=round(s1["final"]["p5"] - s0["final"]["p5"], 2),
                          prob_loss=round(s1["prob_loss"] - s0["prob_loss"], 4)),
        risk_current=_risk_snapshot(prices, bench_s, q0k),
        risk_modified=_risk_snapshot(prices, bench_s, q1),
        excluded=_excl(excluded))

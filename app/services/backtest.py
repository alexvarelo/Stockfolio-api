"""Pure backtest engine (pandas/numpy only, no network).

All trades execute at the daily close in base currency, fractional shares allowed,
cash earns 0. Fees are `fee_bps` of traded notional.
"""
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from app.services import risk

MAX_POINTS = 500
MAX_TRADES = 200


# --- Private indicators. TODO: unify with app/services/technicals.py after merge. ---
def sma(s: pd.Series, window: int) -> pd.Series:
    return s.rolling(window, min_periods=window).mean()


def rsi_wilder(s: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI: ewm(alpha=1/period, adjust=False) of gains/losses."""
    delta = s.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = gain / loss
    out = 100 - 100 / (1 + rs)
    out[(loss == 0) & gain.notna()] = 100.0
    return out
# -----------------------------------------------------------------------------------


def normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
    tot = float(sum(weights.values()))
    return {k: v / tot for k, v in weights.items()}


def _period_key(ts: pd.Timestamp, freq: str):
    if freq == "monthly":
        return (ts.year, ts.month)
    if freq == "quarterly":
        return (ts.year, (ts.month - 1) // 3)
    return (ts.year,)


class _Portfolio:
    """Shares + cash with fee-aware buy/sell helpers; records trades."""

    def __init__(self, tickers: List[str], weights: np.ndarray, fee: float):
        self.tickers = tickers
        self.w = weights
        self.fee = fee
        self.shares = np.zeros(len(tickers))
        self.cash = 0.0
        self.trades: List[dict] = []

    def value(self, p: np.ndarray) -> float:
        return float(self.shares @ p) + self.cash

    def _record(self, date, i, side, qty, price):
        self.trades.append({"date": date, "ticker": self.tickers[i], "side": side,
                            "quantity": float(qty), "price": float(price)})

    def buy_cash(self, date, p: np.ndarray, amount: float):
        """Spend `amount` of cash (fees included) across targets by weight."""
        amount = min(amount, self.cash)
        if amount <= 0:
            return
        notional = amount / (1 + self.fee) * self.w
        for i, n in enumerate(notional):
            if n > 0:
                q = n / p[i]
                self.shares[i] += q
                self._record(date, i, "buy", q, p[i])
        self.cash -= amount

    def sell_all(self, date, p: np.ndarray):
        for i, q in enumerate(self.shares):
            if q > 0:
                self.cash += q * p[i] * (1 - self.fee)
                self._record(date, i, "sell", q, p[i])
        self.shares[:] = 0.0

    def rebalance(self, date, p: np.ndarray):
        v = self.value(p)
        target = self.w * v
        cur = self.shares * p
        diff = target - cur
        for i in np.where(diff < -1e-12)[0]:
            q = -diff[i] / p[i]
            self.shares[i] -= q
            self.cash += -diff[i] * (1 - self.fee)
            self._record(date, i, "sell", q, p[i])
        need = np.where(diff > 1e-12, diff, 0.0)
        cost = float(need.sum()) * (1 + self.fee)
        if cost <= 0:
            return
        scale = min(1.0, self.cash / cost)
        for i in np.where(need > 0)[0]:
            n = need[i] * scale
            q = n / p[i]
            self.shares[i] += q
            self._record(date, i, "buy", q, p[i])
        self.cash -= cost * scale


def simulate_weighted(prices: pd.DataFrame, weights: Dict[str, float], flows: pd.Series,
                      fee_bps: float = 0.0, rebalance_freq: Optional[str] = None) -> dict:
    """Invest `flows` (cash contributed on given dates) at target weights.

    rebalance_freq: if set, rebalance to targets at the first trading day of each new period.
    """
    tickers = list(prices.columns)
    w = np.array([weights[t] for t in tickers], dtype=float)
    pf = _Portfolio(tickers, w, fee_bps / 10_000.0)
    P = prices.to_numpy(dtype=float)
    flow_arr = flows.reindex(prices.index).fillna(0.0).to_numpy(dtype=float)
    values, invested, exposure = [], [], []
    cum = 0.0
    prev_key = None
    for i, ts in enumerate(prices.index):
        p = P[i]
        if flow_arr[i] > 0:
            pf.cash += flow_arr[i]
            cum += flow_arr[i]
            pf.buy_cash(ts, p, flow_arr[i])
        key = _period_key(ts, rebalance_freq) if rebalance_freq else None
        if rebalance_freq and prev_key is not None and key != prev_key:
            pf.rebalance(ts, p)
        prev_key = key
        values.append(pf.value(p))
        invested.append(cum)
        exposure.append(float(pf.shares @ p) > 0)
    return _pack(prices.index, values, invested, exposure, pf.trades, flow_arr)


def simulate_signals(prices: pd.Series, buy_sig: np.ndarray, sell_sig: np.ndarray,
                     initial_capital: float, fee_bps: float = 0.0) -> dict:
    """All-in / all-out on one ticker. A signal on day t executes at the close of day t+1."""
    name = prices.name or "asset"
    pf = _Portfolio([name], np.array([1.0]), fee_bps / 10_000.0)
    pf.cash = initial_capital
    P = prices.to_numpy(dtype=float)
    values, invested, exposure = [], [], []
    flow = np.zeros(len(prices))
    flow[0] = initial_capital
    pending = None
    for i, ts in enumerate(prices.index):
        p = P[i:i + 1]
        if pending == "buy" and pf.shares[0] == 0:
            pf.buy_cash(ts, p, pf.cash)
        elif pending == "sell" and pf.shares[0] > 0:
            pf.sell_all(ts, p)
        pending = "buy" if buy_sig[i] else ("sell" if sell_sig[i] else None)
        values.append(pf.value(p))
        invested.append(initial_capital)
        exposure.append(float(pf.shares @ p) > 0)
    return _pack(prices.index, values, invested, exposure, pf.trades, flow)


def _pack(index, values, invested, exposure, trades, flows) -> dict:
    return {"index": index, "values": np.array(values), "invested": np.array(invested),
            "exposure": np.array(exposure), "trades": trades, "flows": np.asarray(flows)}


def compute_metrics(sim: dict) -> dict:
    v = pd.Series(sim["values"], index=sim["index"])
    flows = pd.Series(sim["flows"], index=sim["index"])
    total_invested = float(sim["invested"][-1])
    final = float(v.iloc[-1])
    # Time-weighted daily returns: (V_t - flow_t) / V_{t-1} - 1
    prev = v.shift(1)
    r = ((v - flows) / prev - 1.0)[prev > 0].dropna()
    cagr = vol = mdd = None
    if len(r) >= 1:
        idx = (1 + r).cumprod()
        days = (v.index[-1] - v.index[0]).days
        if days > 0 and idx.iloc[-1] > 0:
            cagr = float(idx.iloc[-1] ** (365.25 / days) - 1.0)
        full = pd.concat([pd.Series([1.0]), idx.reset_index(drop=True)], ignore_index=True)
        mdd = risk.max_drawdown(full)
    if len(r) >= 2:
        vol = float(r.std(ddof=1) * np.sqrt(risk.TRADING_DAYS))
    return {
        "final_value": final,
        "total_invested": total_invested,
        "total_return": final / total_invested - 1.0 if total_invested > 0 else 0.0,
        "cagr": cagr,
        "max_drawdown": mdd,
        "volatility_annual": vol,
        "trades": len(sim["trades"]),
        "time_in_market": float(sim["exposure"].mean()),
    }


def downsample_indices(n: int, max_points: int = MAX_POINTS) -> List[int]:
    if n <= max_points:
        return list(range(n))
    return sorted(set(np.linspace(0, n - 1, max_points).round().astype(int).tolist()))


def run_backtest(prices: pd.DataFrame, strategy: str, weights: Dict[str, float],
                 start, end, initial_capital: float, monthly_amount: float = 0.0,
                 rebalance_frequency: str = "quarterly", rsi_buy: float = 30.0,
                 rsi_sell: float = 70.0, fast: int = 50, slow: int = 200,
                 fee_bps: float = 0.0) -> dict:
    """prices: aligned base-currency closes; rows before `start` are used only as indicator warm-up."""
    weights = normalize_weights(weights)
    prices = prices[list(weights)]
    mask = (prices.index >= pd.Timestamp(start)) & (prices.index <= pd.Timestamp(end))
    win = prices[mask]
    if len(win) < 2:
        raise ValueError("not enough price data in the requested window")

    if strategy in ("dca", "rebalance"):
        flows = pd.Series(0.0, index=win.index)
        flows.iloc[0] = initial_capital
        if strategy == "dca":
            first_of_month = ~pd.Series(win.index.to_period("M"), index=win.index).duplicated()
            flows[first_of_month] += monthly_amount
        sim = simulate_weighted(win, weights, flows, fee_bps,
                                rebalance_frequency if strategy == "rebalance" else None)
        bench = simulate_weighted(win, weights, flows, fee_bps, None)
    else:
        col = win.columns[0]
        full = prices[col]
        if strategy == "rsi":
            ind = rsi_wilder(full)
            prev = ind.shift(1)
            buy = ((prev >= rsi_buy) & (ind < rsi_buy)).to_numpy()
            sell = ((prev <= rsi_sell) & (ind > rsi_sell)).to_numpy()
        else:
            f, s = sma(full, fast), sma(full, slow)
            d = f - s
            pd_ = d.shift(1)
            buy = ((pd_ <= 0) & (d > 0)).to_numpy()
            sell = ((pd_ >= 0) & (d < 0)).to_numpy()
        buy, sell = buy[mask], sell[mask]
        sim = simulate_signals(win[col], buy, sell, initial_capital, fee_bps)
        flows = pd.Series(0.0, index=win.index)
        flows.iloc[0] = initial_capital
        bench = simulate_weighted(win, weights, flows, fee_bps, None)

    idx = downsample_indices(len(win))
    curve = [{"date": win.index[i].date(), "strategy_value": float(sim["values"][i]),
              "benchmark_value": float(bench["values"][i]), "invested": float(sim["invested"][i])}
             for i in idx]
    trades = [{**t, "date": t["date"].date()} for t in sim["trades"][-MAX_TRADES:]]
    return {
        "start_date": win.index[0].date(), "end_date": win.index[-1].date(),
        "equity_curve": curve,
        "metrics": {"strategy": compute_metrics(sim), "benchmark": compute_metrics(bench)},
        "trades": trades,
        "sim": sim, "bench": bench,
    }

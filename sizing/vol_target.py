import math
from dataclasses import dataclass
from typing import Dict, Tuple
import pandas as pd
import numpy as np

TRADING_DAYS = 252.0


@dataclass
class VolConfig:
    target_annualized: float = 0.20
    lookback_bars: int = 100
    ewma_lambda: float = 0.94
    atr_n: int = 20
    risk_bps_min: float = 5.0
    risk_bps_max: float = 100.0
    dust_threshold_equity_pct: float = 0.0005


def compute_realized_vol_ewma(returns: pd.Series, lookback: int, lam: float) -> pd.Series:
    r2 = returns.fillna(0).pow(2)
    w = np.array([lam**i for i in range(lookback)], dtype=float)
    w = w / w.sum()
    # rolling dot product without leakage
    r2_roll = pd.Series(np.convolve(r2.values, w[::-1], mode="full"))[: len(r2)]
    r2_roll.index = returns.index
    sigma_daily = np.sqrt((1 - lam) * r2_roll.clip(lower=0))
    sigma_annual = sigma_daily * np.sqrt(TRADING_DAYS)
    return sigma_annual


def compute_atr_wilder(ohlc: pd.DataFrame, n: int) -> pd.Series:
    high, low, close = ohlc["high"], ohlc["low"], ohlc["close"]
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / n, adjust=False).mean()
    return atr


def stop_distance_ticks_for_symbol(symbol: str, atr: float, tick_size: float, atr_multiple: float) -> int:
    dist_price = atr_multiple * atr
    ticks = math.ceil(dist_price / tick_size)
    return max(1, ticks)


def size_order_from_risk(
    equity_usd: float, stop_price_distance: float, sigma_ann: float, cfg: VolConfig, k: float
) -> Tuple[float, float]:
    target_vol = cfg.target_annualized
    # Scale so typical sigma in [0.10, 0.40] maps to ~[20, 5] bps at k=1
    risk_bps = k * target_vol / max(sigma_ann, 1e-9) * 10.0
    risk_bps = float(np.clip(risk_bps, cfg.risk_bps_min, cfg.risk_bps_max))
    risk_dollars = equity_usd * (risk_bps / 10000.0)
    qty = risk_dollars / max(stop_price_distance, 1e-9)
    return qty, risk_bps


def calibrate_global_k(daily_returns_fn, bracket=(0.2, 5.0), target=0.20, tol=0.002):
    # simple bisection on k to match realized vol to target
    lo, hi = bracket
    for _ in range(18):
        mid = 0.5 * (lo + hi)
        realized = abs(daily_returns_fn(mid))
        if realized > target:
            hi = mid
        else:
            lo = mid
        if abs(realized - target) < tol:
            break
    return 0.5 * (lo + hi)


def generate_stop_distance_csv(
    features_path: str, tick_sizes: Dict[str, float], atr_multiple_map: Dict[str, float], atr_n: int, out_csv: str
):
    # features.parquet expected per symbol OHLC with a MultiIndex [ts, symbol] or columns including symbol
    df = pd.read_parquet(features_path)
    if "symbol" not in df.columns:
        raise ValueError("features.parquet must include a 'symbol' column")
    rows = []
    for sym, g in df.groupby("symbol"):
        ohlc = g.sort_values("ts")[["high", "low", "close"]]
        atr = compute_atr_wilder(ohlc, n=atr_n).iloc[-1]
        tick = tick_sizes.get(sym, tick_sizes.get("default", 0.01))
        mult = atr_multiple_map.get(sym, atr_multiple_map.get("default", 2.5))
        ticks = stop_distance_ticks_for_symbol(sym, float(atr), float(tick), float(mult))
        rows.append(
            {
                "symbol": sym,
                "tick_size": tick,
                "atr": float(atr),
                "atr_multiple": mult,
                "stop_distance_ticks": int(ticks),
            }
        )
    pd.DataFrame(rows).to_csv(out_csv, index=False)

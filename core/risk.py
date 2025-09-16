# risk.py
"""
Risk management and position sizing functions, including Kelly criterion calculations for sizing trades.
"""
from typing import Dict
from .strategy import kelly_size_from_metrics

def kelly_fraction(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """
    Calculate the Kelly fraction given win probability, average win, and average loss.
    Returns the fraction of capital to risk. Returns 0.0 if inputs are invalid or no edge (e.g., non-positive loss or zero expectancy).
    """
    if avg_loss <= 0 or (avg_win + avg_loss) == 0:
        return 0.0
    b = avg_win / abs(avg_loss)
    p = max(0.0, min(1.0, win_rate))
    q = 1.0 - p
    # Kelly formula: optimal fraction = (b * p - q) / b
    k = (b * p - q) / b
    return max(0.0, k)

def kelly_from_trades(expectancy: float, win_rate: float, shrink: float = 20.0) -> float:
    """
    Approximate the Kelly fraction from expectancy and win rate, using a shrinkage factor to reduce position size.
    Uses a heuristic that assumes average win is ~2 * |average loss| for estimating Kelly fraction.
    """
    p = max(0.0, min(1.0, win_rate))
    denom = max(1e-6, (3 * p - 1.0))
    avg_loss = expectancy / denom if denom != 0 else 0.0
    avg_win = 2.0 * avg_loss
    return float(kelly_fraction(p, avg_win, avg_loss) / max(1.0, shrink))

def clip(value: float, lo: float, hi: float) -> float:
    """Clamp a value between lo and hi inclusive."""
    return max(lo, min(hi, value))

def kelly_size_from_metrics(met_tr: Dict, kelly_on: bool, kelly_min: float,
                             kelly_max: float, kelly_shrink: float, base_risk: float) -> float:
    """
    Determine a position size fraction based on metrics (e.g., training results) and Kelly criterion parameters.
    - If kelly_on is False, return base_risk unchanged.
    - If kelly_on is True, compute a Kelly fraction from metrics, apply shrinkage and clamp between kelly_min and kelly_max (scaled by base_risk).
    """
    if not kelly_on:
        return float(base_risk)
    p = float(met_tr.get("win_rate", 0.0))
    E = float(met_tr.get("expectancy", 0.0))
    k = kelly_from_trades(E, p, shrink=kelly_shrink)
    k = clip(k, kelly_min * base_risk, kelly_max * base_risk)
    return float(k)

from __future__ import annotations
import numpy as np
from typing import Dict, Any
from .types import Signal, Side
from .base import Strategy

try:
    from strategy.ma_crossover import sma as repo_sma  # use your helper if available
except Exception:
    repo_sma = None

def _sma(x: np.ndarray, w: int) -> np.ndarray:
    if repo_sma is not None:
        return repo_sma(x, w)
    if x.size < w:
        return np.full_like(x, np.nan, dtype=float)
    c = np.cumsum(x, dtype=float)
    c[w:] = c[w:] - c[:-w]
    sma = c[w-1:] / w
    pad = np.full(w-1, np.nan, dtype=float)
    return np.concatenate([pad, sma])

class MACrossoverAdapter(Strategy):
    name = "ma_crossover"
    def __init__(self, fast: int = 10, slow: int = 30, ttl: int = 1, stop_lookback: int = 20) -> None:
        self.fast = fast; self.slow = slow; self.ttl = ttl; self.stop_lookback = stop_lookback
    def prepare(self, ctx: Dict[str, Any]) -> None: return None
    def generate_signal(self, market_state: Dict[str, Any]) -> Signal:
        c = np.asarray(market_state["c"], dtype=float)
        h = np.asarray(market_state.get("h", c), dtype=float)
        l = np.asarray(market_state.get("l", c), dtype=float)
        if c.size < max(self.slow, 3): return Signal.hold(self.ttl)
        f = _sma(c, self.fast); s = _sma(c, self.slow)
        if not np.isfinite(f[-1]) or not np.isfinite(s[-1]): return Signal.hold(self.ttl)
        spread = abs(f[-1] - s[-1]); denom = max(1e-9, np.std(c[-self.slow:]))
        strength = float(np.clip(spread/denom, 0.0, 1.0))
        if f[-1] > s[-1]:
            stop = float(np.nanmin(l[-self.stop_lookback:])) if c.size >= self.stop_lookback else None
            return Signal(Side.BUY, strength, stop, self.ttl)
        if f[-1] < s[-1]:
            stop = float(np.nanmax(h[-self.stop_lookback:])) if c.size >= self.stop_lookback else None
            return Signal(Side.SELL, strength, stop, self.ttl)
        return Signal.hold(self.ttl)

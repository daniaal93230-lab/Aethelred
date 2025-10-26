from __future__ import annotations
import numpy as np
from typing import Dict, Any
from .types import Signal, Side
from .base import Strategy

class DonchianBreakout(Strategy):
    name = "donchian_breakout"
    def __init__(self, entry_n: int = 30, exit_n: int = 12, ttl: int = 1):
        self.entry_n = entry_n
        self.exit_n = exit_n
        self.ttl = ttl
    def prepare(self, ctx: Dict[str, Any]) -> None:
        return None
    def generate_signal(self, market_state: Dict[str, Any]) -> Signal:
        c = np.asarray(market_state.get("c", []), dtype=float)
        h = np.asarray(market_state.get("h", c), dtype=float)
        l = np.asarray(market_state.get("l", c), dtype=float)
        if c.size < max(3, self.entry_n):
            return Signal.hold(self.ttl)
        don_high = np.max(h[-self.entry_n:])
        don_low_exit = np.min(l[-self.exit_n:]) if c.size >= self.exit_n else np.min(l)
        if c[-1] > don_high:
            return Signal(Side.BUY, 0.5, float(np.min(l[-self.entry_n:])), self.ttl)
        if c[-1] < don_low_exit:
            return Signal(Side.SELL, 0.5, float(np.max(h[-self.exit_n:])), self.ttl)
        return Signal.hold(self.ttl)

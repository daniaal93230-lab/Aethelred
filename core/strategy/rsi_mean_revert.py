from __future__ import annotations
import numpy as np
from typing import Dict, Any
from .types import Signal, Side
from .base import Strategy

class RSIMeanRevert(Strategy):
    name = "rsi_mean_revert"
    def __init__(self, rsi_len: int = 14, rsi_buy: int = 30, ttl: int = 1):
        self.rsi_len = rsi_len
        self.rsi_buy = rsi_buy
        self.ttl = ttl
    def prepare(self, ctx: Dict[str, Any]) -> None:
        return None
    def _rsi(self, c: np.ndarray) -> float:
        # simple last-RSI calculator
        if c.size < 2:
            return 50.0
        delta = np.diff(c)
        gain = np.where(delta > 0, delta, 0.0)
        loss = np.where(delta < 0, -delta, 0.0)
        avg_gain = gain.mean() if gain.size else 0.0
        avg_loss = loss.mean() if loss.size else 1e-9
        rs = avg_gain / (avg_loss if avg_loss > 0 else 1e-9)
        return 100.0 - (100.0 / (1.0 + rs))
    def generate_signal(self, market_state: Dict[str, Any]) -> Signal:
        c = np.asarray(market_state.get("c", []), dtype=float)
        if c.size < max(3, self.rsi_len):
            return Signal.hold(self.ttl)
        last_rsi = self._rsi(c[-self.rsi_len:])
        if last_rsi < self.rsi_buy:
            return Signal(Side.BUY, float(min(1.0, (self.rsi_buy - last_rsi) / self.rsi_buy)), None, self.ttl)
        return Signal.hold(self.ttl)

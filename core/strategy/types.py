from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional

class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

@dataclass(frozen=True)
class Signal:
    side: Side
    strength: float
    stop_hint: Optional[float]
    ttl: int

    @staticmethod
    def hold(ttl: int = 1) -> "Signal":
        return Signal(Side.HOLD, 0.0, None, ttl)

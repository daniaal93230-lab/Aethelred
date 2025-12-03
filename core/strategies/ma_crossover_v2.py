from __future__ import annotations

from decimal import Decimal, getcontext
from typing import List, Dict, Any

getcontext().prec = 28


def sma(vals: List[float], period: int) -> Decimal:
    if len(vals) < period:
        return Decimal("0")
    d = [Decimal(str(x)) for x in vals[-period:]]
    return sum(d) / Decimal(str(period))


def ma_crossover_v2(closes: List[float]) -> Dict[str, Any]:
    """
    S3 API moving-average crossover strategy.
    """
    fast = sma(closes, period=10)
    slow = sma(closes, period=30)
    price = Decimal(str(closes[-1]))

    if fast > slow:
        intent = "long"
        strength = (fast - slow) / slow if slow > 0 else Decimal("0")
        stop = price * Decimal("0.97")
    elif fast < slow:
        intent = "short"
        strength = (slow - fast) / slow if slow > 0 else Decimal("0")
        stop = price * Decimal("1.03")
    else:
        intent = "flat"
        strength = Decimal("0")
        stop = price

    return {
        "intent": intent,
        "entry_price": price,
        "exit_price": price,
        "stop": stop,
        "strength": strength,
        "probabilities": {
            "transition": float(strength),
        },
        "confidence": {
            "pattern": float(strength),
        },
        "meta": {
            "fast_ma": float(fast),
            "slow_ma": float(slow),
        },
    }

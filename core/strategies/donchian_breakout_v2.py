from __future__ import annotations

from decimal import Decimal, getcontext
from typing import List, Dict, Any

getcontext().prec = 28


def donchian(highs: List[float], lows: List[float], period: int = 20):
    if len(highs) < period:
        return None, None
    high_d = [Decimal(str(x)) for x in highs[-period:]]
    low_d = [Decimal(str(x)) for x in lows[-period:]]
    return max(high_d), min(low_d)


def donchian_breakout_v2(highs: List[float], lows: List[float], closes: List[float]) -> Dict[str, Any]:
    """
    S3 API breakout strategy.
    """
    upper, lower = donchian(highs, lows, period=20)
    price = Decimal(str(closes[-1]))

    if upper is None or lower is None:
        return {
            "intent": "flat",
            "entry_price": price,
            "exit_price": price,
            "stop": price,
            "strength": Decimal("0"),
            "probabilities": {},
            "confidence": {},
            "meta": {},
        }

    if price >= upper:
        intent = "long"
        strength = (price - upper) / upper if upper > 0 else Decimal("0")
        stop = lower
    elif price <= lower:
        intent = "short"
        strength = (lower - price) / lower if lower > 0 else Decimal("0")
        stop = upper
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
            "trend_continuation": float(strength),
        },
        "confidence": {
            "pattern": float(strength),
        },
        "meta": {
            "upper": float(upper),
            "lower": float(lower),
        },
    }

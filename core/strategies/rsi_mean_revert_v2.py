from __future__ import annotations

from decimal import Decimal, getcontext
from typing import List, Dict, Any

getcontext().prec = 28


def rsi(closes: List[float], period: int = 14) -> Decimal:
    if len(closes) < period + 1:
        return Decimal("50")

    gains = []
    losses = []

    for i in range(1, period + 1):
        diff = Decimal(str(closes[-i])) - Decimal(str(closes[-i - 1]))
        if diff > 0:
            gains.append(diff)
        else:
            losses.append(abs(diff))

    avg_gain = sum(gains) / Decimal(str(period)) if gains else Decimal("0.0001")
    avg_loss = sum(losses) / Decimal(str(period)) if losses else Decimal("0.0001")

    rs = avg_gain / avg_loss
    return Decimal("100") - (Decimal("100") / (Decimal("1") + rs))


def rsi_mean_revert_v2(closes: List[float]) -> Dict[str, Any]:
    """
    S3 API response for RSI mean-reversion strategy.
    """
    r = rsi(closes)
    price = Decimal(str(closes[-1]))

    # Thresholds (deterministic defaults)
    buy_thr = Decimal("30")
    sell_thr = Decimal("70")

    if r <= buy_thr:
        intent = "long"
        strength = (buy_thr - r) / buy_thr
        stop = price * Decimal("0.97")
    elif r >= sell_thr:
        intent = "short"
        strength = (r - sell_thr) / sell_thr
        stop = price * Decimal("1.03")
    else:
        intent = "flat"
        strength = Decimal("0")
        stop = price

    return {
        "intent": intent,
        "entry_price": price,
        "exit_price": price,  # basic version — real exits in Phase 4.B
        "stop": stop,
        "strength": strength,
        "probabilities": {
            "range_reversion": float(strength),
        },
        "confidence": {
            "pattern": float(strength),
        },
        "meta": {
            "rsi": float(r),
        },
    }

"""
Legacy test stub for EMA trend strategy.

Required by:
    from strategy.ema_trend import signal as sig_trend

This file is NOT used in production. It only provides a simple,
deterministic EMA-based signal() for legacy selector tests.
"""

from __future__ import annotations

from typing import Dict, Any
import numpy as np


def signal(market: Dict[str, Any]) -> Dict[str, Any]:
    """
    Minimal EMA trend signal expected by tests.

    Returns:
        dict(side="buy"/"sell"/"hold", strength=float)
    """
    prices = market.get("close", [])
    if not prices:
        return {"side": "hold", "strength": 0.0}

    arr = np.array(prices, dtype=float)

    # Compute simple EMA
    alpha = 2 / (len(arr) + 1)
    ema = arr[0]
    for p in arr[1:]:
        ema = alpha * p + (1 - alpha) * ema

    last = arr[-1]

    if last > ema:
        return {"side": "buy", "strength": float(last - ema)}
    if last < ema:
        return {"side": "sell", "strength": float(ema - last)}

    return {"side": "hold", "strength": 0.0}


__all__ = ["signal"]

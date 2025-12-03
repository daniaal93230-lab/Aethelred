from __future__ import annotations

from decimal import Decimal, getcontext
from typing import Optional

import pandas as pd

from core.strategy.types import Signal, Side

getcontext().prec = 28


def _d(v) -> Decimal:
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal("0")


def _sma(series, length: int) -> Optional[Decimal]:
    if len(series) < length:
        return None
    return _d(sum(series[-length:]) / length)


def _ema(series, length: int) -> Optional[Decimal]:
    if len(series) < length:
        return None
    alpha = _d(2) / _d(length + 1)
    ema = _d(series[-length])
    for v in series[-length + 1 :]:
        ema = alpha * _d(v) + (Decimal("1") - alpha) * ema
    return ema


def ma_crossover(
    df: pd.DataFrame,
    fast: int = 10,
    slow: int = 20,
    mode: str = "sma",     # "sma" or "ema"
    ttl: int = 2
) -> Signal:
    """
    Canonical MA crossover strategy for Aethelred v2.

    Regime: transitional

    Logic:
      • BUY  when fast MA > slow MA
      • SELL when fast MA < slow MA
      • HOLD when equal or insufficient data

    Strength = |fast - slow| / slow
    TTL      = time-to-live override
    """

    try:
        if df is None or df.empty:
            return Signal(side=Side.HOLD, strength=Decimal("0"), stop_hint=None, ttl=ttl)

        closes = df["close"].astype(float).tolist()

        # MA selection
        if mode.lower() == "ema":
            fast_ma = _ema(closes, fast)
            slow_ma = _ema(closes, slow)
        else:
            fast_ma = _sma(closes, fast)
            slow_ma = _sma(closes, slow)

        # Not enough data
        if fast_ma is None or slow_ma is None:
            return Signal(side=Side.HOLD, strength=Decimal("0"), stop_hint=None, ttl=ttl)

        # Sides
        if fast_ma > slow_ma:
            strength = (fast_ma - slow_ma) / (slow_ma if slow_ma != 0 else fast_ma)
            return Signal(
                side=Side.BUY,
                strength=strength,
                stop_hint=slow_ma,   # lower MA acts as stop reference
                ttl=ttl,
            )

        if fast_ma < slow_ma:
            strength = (slow_ma - fast_ma) / (fast_ma if fast_ma != 0 else slow_ma)
            return Signal(
                side=Side.SELL,
                strength=strength,
                stop_hint=fast_ma,   # higher MA acts as stop reference
                ttl=ttl,
            )

        # MA equal → HOLD
        return Signal(
            side=Side.HOLD,
            strength=Decimal("0"),
            stop_hint=None,
            ttl=ttl,
        )

    except Exception:
        return Signal(side=Side.HOLD, strength=Decimal("0"), stop_hint=None, ttl=ttl)


__all__ = ["ma_crossover"]

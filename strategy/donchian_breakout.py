from __future__ import annotations

from decimal import Decimal, getcontext
from dataclasses import dataclass
from typing import Optional, Sequence

import pandas as pd

from core.strategy.types import Signal, Side

# High-precision arithmetic for breakouts
getcontext().prec = 28


def _decimal(v) -> Decimal:
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal("0")


def donchian_breakout(
    df: pd.DataFrame,
    lookback: int = 20,
    ttl: int = 3
) -> Signal:
    """
    Production Donchian breakout strategy.

    Rules:
      • BUY  when close breaks above the max(high[-lookback:])
      • SELL when close breaks below the min(low[-lookback:])
      • HOLD otherwise

    Strength = % distance from breakout channel mid-point.
    TTL      = strategy-level time-to-live override.

    All arithmetic uses Decimal for deterministic correctness.
    """
    try:
        if df is None or df.empty or len(df) < lookback + 1:
            return Signal(side=Side.HOLD, strength=Decimal("0"), stop_hint=None, ttl=ttl)

        highs = df["high"].astype(float).tolist()
        lows = df["low"].astype(float).tolist()
        closes = df["close"].astype(float).tolist()

        recent_high = _decimal(max(highs[-lookback:]))
        recent_low = _decimal(min(lows[-lookback:]))
        close = _decimal(closes[-1])

        # Channel mid for magnitude estimation
        mid = (recent_high + recent_low) / Decimal("2")
        if mid == 0:
            mid = close

        # BUY breakout
        if close > recent_high:
            strength = (close - recent_high) / mid
            return Signal(
                side=Side.BUY,
                strength=strength,
                stop_hint=recent_low,   # Donchian stop is lower band
                ttl=ttl
            )

        # SELL breakout
        if close < recent_low:
            strength = (recent_low - close) / mid
            return Signal(
                side=Side.SELL,
                strength=strength,
                stop_hint=recent_high,  # Donchian stop is upper band
                ttl=ttl
            )

        # HOLD
        return Signal(
            side=Side.HOLD,
            strength=Decimal("0"),
            stop_hint=None,
            ttl=ttl
        )

    except Exception:
        return Signal(side=Side.HOLD, strength=Decimal("0"), stop_hint=None, ttl=ttl)


__all__ = ["donchian_breakout"]

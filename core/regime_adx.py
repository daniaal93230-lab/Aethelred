from __future__ import annotations

from decimal import Decimal, getcontext
from dataclasses import dataclass
from typing import Optional, Sequence

import pandas as pd

# High precision for ADX calculations
getcontext().prec = 28


@dataclass
class RegimeADX:
    label: str            # "trend" | "chop" | "transition"
    adx: Decimal
    threshold_low: Decimal = Decimal("20")
    threshold_high: Decimal = Decimal("25")


def compute_adx(df: pd.DataFrame, n: int = 14) -> Optional[Decimal]:
    """
    Compute ADX using Decimal. Returns Decimal or None.

    df must contain columns: high, low, close.
    """
    try:
        if df is None or df.empty:
            return None

        highs = df["high"].astype(float)
        lows = df["low"].astype(float)
        closes = df["close"].astype(float)

        # Price movements
        up_move = highs.diff()
        down_move = lows.shift().diff()

        # True range
        tr1 = highs - lows
        tr2 = (highs - closes.shift()).abs()
        tr3 = (lows - closes.shift()).abs()

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # Smoothed TR
        tr_smooth = tr.rolling(n).sum()
        # +DM / -DM
        plus_dm = ((up_move > 0) & (up_move > down_move)).astype(int) * up_move
        minus_dm = ((down_move > 0) & (down_move > up_move)).astype(int) * (-down_move)

        plus_dm_smooth = plus_dm.rolling(n).sum()
        minus_dm_smooth = minus_dm.rolling(n).sum()

        # DIs
        plus_di = (plus_dm_smooth / tr_smooth) * 100
        minus_di = (minus_dm_smooth / tr_smooth) * 100

        # DX
        dx = ((plus_di - minus_di).abs() / (plus_di + minus_di)) * 100

        # ADX = smoothed DX
        adx = dx.rolling(n).mean()

        val = adx.iloc[-1]
        if pd.isna(val):
            return None

        return Decimal(str(round(float(val), 6)))

    except Exception:
        return None


def compute_regime_adx(df: pd.DataFrame) -> RegimeADX:
    """
    Returns a typed RegimeADX object.
    """
    adx_val = compute_adx(df)
    if adx_val is None:
        return RegimeADX(label="normal", adx=Decimal("0"))

    if adx_val >= Decimal("25"):
        return RegimeADX(label="trend", adx=adx_val)

    if adx_val <= Decimal("20"):
        return RegimeADX(label="chop", adx=adx_val)

    return RegimeADX(label="transition", adx=adx_val)

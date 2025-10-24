from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
import pandas as pd

Label = Literal["trend", "chop", "panic", "unknown"]

@dataclass
class Regime:
    label: Label
    vol_z: float
    ema_slope: float

def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def _realized_vol(close: pd.Series, lb: int) -> pd.Series:
    r = close.pct_change().fillna(0.0)
    return r.rolling(lb, min_periods=max(2, lb // 2)).std()

def _z(s: pd.Series, lb: int) -> pd.Series:
    m = s.rolling(lb, min_periods=max(2, lb // 2)).mean()
    v = s.rolling(lb, min_periods=max(2, lb // 2)).std()
    return (s - m) / v.replace(0.0, pd.NA)

def compute_regime(df: pd.DataFrame) -> Regime:
    """
    Classify a simple regime from OHLCV DataFrame with 'close' column.
      panic: vol_z >= 2.0
      trend: abs(ema_slope) >= slope_thr and vol_z < 2.0
      chop:  otherwise
      unknown: insufficient data
    """
    if df is None or len(df) < 20 or "close" not in df:
        return Regime("unknown", 0.0, 0.0)

    c = df["close"].astype(float)
    vol = _realized_vol(c, lb=30)
    volz = _z(vol, lb=60)
    ema_fast = _ema(c, n=12)
    slope = float((ema_fast - ema_fast.shift(3)).iloc[-1]) if len(ema_fast) >= 4 else 0.0
    # Fill potential NA from early-window division before casting; ensure float dtype
    vz_series = pd.to_numeric(volz, errors="coerce").fillna(0.0)
    vz = float(vz_series.iloc[-1]) if len(vz_series) else 0.0

    if vz >= 2.0:
        return Regime("panic", vz, slope)
    slope_thr = max(1e-6, 0.0005 * c.iloc[-1])  # small, price-scaled slope band
    if abs(slope) >= slope_thr:
        return Regime("trend", vz, slope)
    return Regime("chop", vz, slope)

from __future__ import annotations
import pandas as pd

def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    r = close.diff()
    up = r.clip(lower=0.0).rolling(n, min_periods=max(2, n//2)).mean()
    dn = (-r.clip(upper=0.0)).rolling(n, min_periods=max(2, n//2)).mean()
    rs = up / dn.replace(0.0, pd.NA)
    return 100.0 - 100.0 / (1.0 + rs)

def signal(df: pd.DataFrame) -> str:
    """
    Mean reversion bands:
      RSI < 30 → buy
      RSI > 70 → sell
      else hold
    """
    if df is None or len(df) < 30:
        return "hold"
    c = df["close"].astype(float)
    r = _rsi(c, 14)
    last = float(r.fillna(50.0).iloc[-1])
    if last < 30.0:
        return "buy"
    if last > 70.0:
        return "sell"
    return "hold"

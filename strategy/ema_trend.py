from __future__ import annotations
import pandas as pd

def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def signal(df: pd.DataFrame) -> str:
    """
    Simple trend follower:
      long when EMA12 > EMA26, short when <, else hold
    """
    if df is None or len(df) < 30:
        return "hold"
    c = df["close"].astype(float)
    f = _ema(c, 12)
    s = _ema(c, 26)
    if float(f.iloc[-1]) > float(s.iloc[-1]):
        return "buy"
    if float(f.iloc[-1]) < float(s.iloc[-1]):
        return "sell"
    return "hold"

from __future__ import annotations
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    r = close.diff()
    up = r.clip(lower=0.0).rolling(n, min_periods=max(2, n // 2)).mean()
    dn = (-r.clip(upper=0.0)).rolling(n, min_periods=max(2, n // 2)).mean()
    rs = up / dn.replace(0.0, pd.NA)
    return 100.0 - 100.0 / (1.0 + rs)


def basic_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a compact feature frame with:
      ema12, ema26, ema_slope, rsi14, vol30
    NaNs forward-filled minimally.
    """
    c = df["close"].astype(float)
    f = ema(c, 12)
    s = ema(c, 26)
    ema_slope = f.diff()
    r = rsi(c, 14)
    vol = c.pct_change().rolling(30, min_periods=10).std()
    out = pd.DataFrame({
        "ema12": f,
        "ema26": s,
        "ema_slope": ema_slope,
        "rsi14": r,
        "vol30": vol,
    })
    out = out.ffill().fillna(0.0)
    return out

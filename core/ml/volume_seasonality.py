# core/ml/volume_seasonality.py
import pandas as pd

def first_minute_z(df: pd.DataFrame) -> float:
    """
    Minute-of-day seasonality proxy. Assumes df indexed by UTC ts or has a DatetimeIndex.
    Returns z-score of the last bar's volume vs same minute-of-day over a rolling 30-day window.
    """
    if df is None or df.empty or "volume" not in df.columns:
        return 0.0
    s = df["volume"].copy()
    if not isinstance(s.index, pd.DatetimeIndex):
        try:
            idx = pd.to_datetime(df.index, utc=True)
            s.index = idx
        except Exception:
            return 0.0
    key = s.index.strftime("%H:%M")
    ref_minute = key[-1]
    ref = s[key == ref_minute]
    if ref.empty:
        return 0.0
    # 30 days of minutes ~ 43,200 bars at 1m; cap to available window
    win = min(len(ref), 30*24*60)
    mu = ref.rolling(win, min_periods=min(60, win)).mean().iloc[-1]
    sd = ref.rolling(win, min_periods=min(60, win)).std().iloc[-1]
    if sd and sd != 0:
        z = (ref.iloc[-1] - mu) / sd
    else:
        z = 0.0
    try:
        return float(z)
    except Exception:
        return 0.0

# strategy/donchian_close.py
import pandas as pd
from typing import Dict, Any, Tuple

NAME = "donchian_close"


def params_default() -> Dict[str, Any]:
    return {"n": 55}


def _bands_close(df: pd.DataFrame, n: int) -> Tuple[pd.Series, pd.Series]:
    closes = df["close"].astype(float)
    up = closes.rolling(n).max().shift(1)
    dn = closes.rolling(n).min().shift(1)
    return up, dn


def signal(df: pd.DataFrame, params: Dict[str, Any] | None = None) -> str:
    params = params or params_default()
    n = int(params.get("n", 55))
    if df is None or df.empty or (len(df) < n + 2):
        return "hold"
    if "close" not in df.columns:
        return "hold"
    up, dn = _bands_close(df, n)
    c = float(df["close"].iloc[-1])
    if pd.isna(up.iloc[-1]) or pd.isna(dn.iloc[-1]):
        return "hold"
    if c > float(up.iloc[-1]):
        return "buy"
    if c < float(dn.iloc[-1]):
        return "sell"
    return "hold"

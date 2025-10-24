# strategy/pairs_threshold_revert.py
import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple

NAME = "pairs_threshold_revert"

def params_default() -> Dict[str, Any]:
    return {"L": 100, "tau": 1.5}

def _norm_series(close: pd.Series, L: int) -> pd.Series:
    close = close.astype(float)
    ma = close.rolling(L).mean()
    vol = close.diff().abs().rolling(L).mean()
    s = (close - ma) / (vol * np.sqrt(L))
    return s

def signal_pair(eth: pd.DataFrame, btc: pd.DataFrame, params: Dict[str, Any] | None = None) -> Tuple[str, float]:
    params = params or params_default()
    L = int(params.get("L", 100))
    tau = float(params.get("tau", 1.5))
    if eth is None or btc is None or eth.empty or btc.empty:
        return "hold", 0.0
    if len(eth) < L + 5 or len(btc) < L + 5:
        return "hold", 0.0
    x = _norm_series(eth["close"], L).iloc[-1]
    y = _norm_series(btc["close"], L).iloc[-1]
    d = float(x - y)
    if d < -tau:
        return "buy", abs(d)
    if d > tau:
        return "sell", abs(d)
    return "hold", 0.0

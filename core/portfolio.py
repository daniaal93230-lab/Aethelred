from __future__ import annotations
import pandas as pd
from typing import Dict, Iterable


def rolling_corr_guard(
    returns_map: Dict[str, pd.Series],
    new_symbol: str,
    held_symbols: Iterable[str],
    lookback: int = 1440,   # 24h if 1m bars
    threshold: float = 0.85,
    new_weight: float = 1.0,
    portfolio_exposure: float = 0.0,
) -> float:
    """
    Correlation-aware guard that returns an adjusted weight for a proposed new position.

    - If correlation with any held symbol exceeds the threshold and portfolio_exposure is
      high, the returned weight is reduced proportionally to (1 - corr).
    - Otherwise returns `new_weight` unchanged.

    This keeps backward compatibility with callers that treat the result truthily
    (non-zero => ok to proceed; zero => skip).
    """
    if not held_symbols:
        return new_weight
    if new_symbol not in returns_map:
        return new_weight
    r_new = returns_map[new_symbol].tail(lookback).dropna()
    if r_new.empty:
        return new_weight
    for s in held_symbols:
        r_old = returns_map.get(s)
        if r_old is None:
            continue
        r_old = r_old.tail(lookback).dropna()
        if r_old.empty:
            continue
        corr = r_new.corr(r_old)
        if pd.notna(corr) and corr > 0.8 and portfolio_exposure > 0.5:
            # reduce the proposed weight when highly correlated and portfolio exposure is high
            return new_weight * (1 - corr)
    return new_weight

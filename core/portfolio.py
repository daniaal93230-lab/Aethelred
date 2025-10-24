from __future__ import annotations
import pandas as pd
from typing import Dict, Iterable


def rolling_corr_guard(
    returns_map: Dict[str, pd.Series],
    new_symbol: str,
    held_symbols: Iterable[str],
    lookback: int = 1440,   # 24h if 1m bars
    threshold: float = 0.85
) -> bool:
    """
    True if it is OK to enter new_symbol alongside held_symbols.
    If any pair corr(new_symbol, held) >= threshold, return False.
    Assumes returns_map contains aligned Series of percentage returns.
    """
    if not held_symbols:
        return True
    if new_symbol not in returns_map:
        return True
    r_new = returns_map[new_symbol].tail(lookback).dropna()
    if r_new.empty:
        return True
    for s in held_symbols:
        r_old = returns_map.get(s)
        if r_old is None:
            continue
        r_old = r_old.tail(lookback).dropna()
        if r_old.empty:
            continue
        corr = r_new.corr(r_old)
        if pd.notna(corr) and corr >= threshold:
            return False
    return True

try:
    from core.evaluator import *  # re-export
except ImportError:
    import pandas as pd
    from typing import Optional
    from .strategy import walk_forward_select, WFSelParams, equity_curve

    def last_signal_within(sig: pd.Series, bars: int):
        sig = sig.astype(int)
        if len(sig) == 0:
            return 0, 10**9
        last_val = int(sig.iloc[-1])
        changes = sig.ne(sig.shift()).to_numpy().nonzero()[0]
        if len(changes) == 0:
            return last_val, 10**9
        last_change_idx = changes[-1]
        age = len(sig) - 1 - last_change_idx
        return last_val, age

    def last_entry_price(close: pd.Series, sig: pd.Series, side_now: int) -> Optional[float]:
        if side_now == 0 or len(sig) == 0:
            return None
        sig = sig.astype(int)
        for i in range(len(sig)-1, 0, -1):
            if sig.iat[i] == side_now and sig.iat[i-1] == 0:
                return float(close.iat[i])
            if sig.iat[i] == 0:
                break
        return None

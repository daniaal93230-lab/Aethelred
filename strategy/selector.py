from __future__ import annotations
import pandas as pd
from typing import Tuple, Callable
from strategy import ma_crossover  # keep existing
from strategy import ema_trend, rsi_mean_revert
from strategy import donchian_close
import os


def pick_by_regime(regime_label: str) -> Tuple[str, Callable[[pd.DataFrame], str]]:
    """
    Map regime to strategy.
      trend -> EMA trend follower
      chop  -> RSI mean reversion
      panic -> blocked (hold)
      unknown -> fallback to ma_crossover
    Returns (name, callable)
    """
    if regime_label == "trend":
        # Default remains ema_trend to keep behavior/tests stable.
        # Opt-in to Donchian via env USE_DONCHIAN=1 (or AET_USE_DONCHIAN=1).
        use_dc = (os.getenv("USE_DONCHIAN", "0").lower() in ("1","true","yes")) or \
                 (os.getenv("AET_USE_DONCHIAN", "0").lower() in ("1","true","yes"))
        if use_dc:
            def _dc(df: pd.DataFrame) -> str:
                try:
                    return donchian_close.signal(df, donchian_close.params_default())
                except Exception:
                    return "hold"
            return "donchian_close", _dc
        return "ema_trend", ema_trend.signal
    if regime_label == "chop":
        return "rsi_mean_revert", rsi_mean_revert.signal
    if regime_label == "panic":
        return "blocked", lambda df: "hold"
    # fallback to existing moving average crossover signal if available
    def _fallback(df: pd.DataFrame) -> str:
        try:
            res = ma_crossover.moving_average_crossover(df)
            # interpret last signal
            sig = int(res["signal"].iloc[-1])
            return "buy" if sig > 0 else ("sell" if sig < 0 else "hold")
        except Exception:
            return "hold"
    return "ma_crossover", _fallback

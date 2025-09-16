# strategies.py
"""
Trading strategy definitions and signal generation functions.
Includes moving average crossover (MA_X) as an example strategy, and utilities for applying regime filters.
"""

from dataclasses import dataclass
from typing import Dict
import numpy as np
import pandas as pd
from .indicators import ema  # using EMA from indicators for MA crossover

@dataclass
class StrategyConfig:
    """Configuration for a trading strategy (name and parameters)."""
    name: str
    params: Dict[str, int]

def ma_x_signal(close: pd.Series, fast: int, slow: int) -> pd.Series:
    """
    Moving Average Crossover signal: +1 for long, -1 for short, 0 for no position.
    Uses two EMAs (fast and slow) on the close price series.
    """
    if fast >= slow:
        # Ensure fast period is shorter than slow period for a valid crossover
        raise ValueError(f"Invalid MA crossover periods: fast({fast}) >= slow({slow})")
    fast_ema = ema(close, fast)
    slow_ema = ema(close, slow)
    # Raw signal: 1 where fast EMA > slow EMA, -1 where fast < slow, 0 otherwise
    raw_signal = (fast_ema > slow_ema).astype(int) - (fast_ema < slow_ema).astype(int)
    # Forward-fill to maintain last signal direction until a flip occurs
    signal = raw_signal.replace(0, np.nan).ffill().fillna(0).astype(int)
    return signal

def apply_regime_filter(sig: pd.Series, adx_series: pd.Series, threshold: float,
                        allow_long: bool = True, allow_short: bool = True) -> pd.Series:
    """
    Filter a raw signal series based on trend regime (using ADX) and allowed directions.
    - Signals are set to 0 (flat) when ADX is below the given threshold (weak trend).
    - If allow_long is False, long signals are suppressed.
    - If allow_short is False, short signals are suppressed.
    The resulting signal is forward-filled so positions are held between signal changes.
    """
    gated = sig.copy()
    # Remove signals during low trend-strength regimes
    gated[adx_series < threshold] = 0
    # Enforce allowed directions
    if not allow_long:
        gated[gated > 0] = 0
    if not allow_short:
        gated[gated < 0] = 0
    # Persist last non-zero signal through periods of 0 to avoid exiting until a reversal signal comes
    filtered_signal = gated.replace(0, np.nan).ffill().fillna(0).astype(int)
    return filtered_signal

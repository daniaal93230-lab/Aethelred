# indicators.py
"""
Technical indicators for analyzing price data.
Includes EMA (Exponential Moving Average), RMA (Wilder's moving average), and ADX (Average Directional Index).
"""

import numpy as np
import pandas as pd
from .strategy import adx

def ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential Moving Average (EMA) of a series over a given span."""
    # Using pandas ewm (exponential weighted function) for EMA. min_periods ensures no values until span is accumulated.
    return series.ewm(span=span, adjust=False, min_periods=span).mean()

def rma(series: pd.Series, length: int) -> pd.Series:
    """Wilder's Moving Average (RMA), an exponential moving average with alpha = 1/length."""
    # Wilder's smoothing uses an exponential weighting equivalent to alpha = 1/length.
    return series.ewm(alpha=1.0 / length, adjust=False).mean()

def adx(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    """
    Calculate the Average Directional Index (ADX) over `length` periods using high, low, close series.
    ADX indicates trend strength (usually combined with DI+ and DI- for direction).
    Returns a series of ADX values.
    """
    # Calculate directional movement (DM) components
    plus_dm = high.diff().clip(lower=0.0)
    minus_dm = (-low.diff()).clip(lower=0.0)
    # Only one of plus_dm or minus_dm is considered each period (whichever is larger)
    plus_dm[plus_dm < minus_dm] = 0.0
    minus_dm[minus_dm < plus_dm] = 0.0

    # True range (TR) components
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Average True Range (ATR) using Wilder's smoothing
    atr = rma(tr, length)
    # Directional Indices
    plus_di = 100 * rma(plus_dm, length) / atr.replace(0, np.nan)
    minus_di = 100 * rma(minus_dm, length) / atr.replace(0, np.nan)
    # DX: Directional Movement Index (absolute difference normalized by sum)
    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)).fillna(0.0)
    # ADX: smoothed DX
    adx_series = rma(dx, length).fillna(0.0)
    return adx_series

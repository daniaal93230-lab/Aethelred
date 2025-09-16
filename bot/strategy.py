# bot/strategy.py
# Core technical indicator helpers and simple strategy signals.

from __future__ import annotations
import numpy as np
import pandas as pd


def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False, min_periods=span).mean()


def adx(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    """
    Wilder's ADX simplified.
    """
    high = high.astype(float)
    low = low.astype(float)
    close = close.astype(float)

    plus_dm = (high.diff().clip(lower=0.0)).where(high.diff() > low.diff(), 0.0)
    minus_dm = (low.diff().abs().clip(lower=0.0)).where(low.diff() > high.diff(), 0.0)

    tr = pd.concat([
        (high - low),
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)

    atr = tr.rolling(length).mean()
    plus_di = 100 * (plus_dm.rolling(length).sum() / atr.replace(0, np.nan))
    minus_di = 100 * (minus_dm.rolling(length).sum() / atr.replace(0, np.nan))
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_val = dx.rolling(length).mean().fillna(0.0)
    return adx_val.fillna(0.0)


def ma_x_signal(close: pd.Series, fast: int = 20, slow: int = 50, allow_long: bool = True, allow_short: bool = False) -> pd.Series:
    fast_ma = _ema(close, fast)
    slow_ma = _ema(close, slow)
    long_sig = (fast_ma > slow_ma).astype(int) if allow_long else 0
    short_sig = -((fast_ma < slow_ma).astype(int)) if allow_short else 0
    sig = long_sig + short_sig
    return sig.clip(-1, 1).fillna(0).astype(int)


def donchian_signal(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 80, allow_long: bool = True, allow_short: bool = False) -> pd.Series:
    hi = high.rolling(n).max()
    lo = low.rolling(n).min()
    long_sig = (close > hi.shift()).astype(int) if allow_long else 0
    short_sig = -((close < lo.shift()).astype(int)) if allow_short else 0
    sig = long_sig + short_sig
    return sig.clip(-1, 1).fillna(0).astype(int)


def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    roll_up = up.ewm(alpha=1/length, adjust=False).mean()
    roll_down = down.ewm(alpha=1/length, adjust=False).mean()
    rs = roll_up / (roll_down.replace(0, np.nan))
    rsi_val = 100 - (100 / (1 + rs))
    return rsi_val.fillna(50.0)


def rsi_mr_signal(close: pd.Series, rsi_len: int = 14, os: int = 30, ob: int = 70, allow_long: bool = True, allow_short: bool = False) -> pd.Series:
    r = rsi(close, rsi_len)
    long_sig = (r < os).astype(int) if allow_long else 0
    short_sig = -((r > ob).astype(int)) if allow_short else 0
    sig = long_sig + short_sig
    return sig.clip(-1, 1).fillna(0).astype(int)


# Back-compat alias to satisfy older imports/tutorials
def moving_average_crossover(close: pd.Series, fast: int = 20, slow: int = 50, allow_long: bool = True, allow_short: bool = False) -> pd.Series:
    return ma_x_signal(close, fast=fast, slow=slow, allow_long=allow_long, allow_short=allow_short)

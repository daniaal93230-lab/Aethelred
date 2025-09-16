# bot/autoparams.py
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Dict

import numpy as np
import pandas as pd


# ───────────────────────────────────────────────────────────────────────────────
# Dataclass describing suggested parameters
# ───────────────────────────────────────────────────────────────────────────────

@dataclass
class SuggestedParams:
    wf_train: int
    wf_test: int
    wf_step: int
    adx_th: float
    adx_len: int


# ───────────────────────────────────────────────────────────────────────────────
# Basic TA helpers (ATR / ADX) – short, dependency-light
# ───────────────────────────────────────────────────────────────────────────────

def _atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    """Average True Range (simple rolling mean of True Range)."""
    prev_close = close.shift(1)
    tr1 = (high - low).abs()
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=n).mean()


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    """Classic ADX calculation (Wilder smoothing approximated with EMA)."""
    up_move = high.diff()
    dn_move = -low.diff()

    plus_dm = np.where((up_move > dn_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((dn_move > up_move) & (dn_move > 0), dn_move, 0.0)

    tr = _atr(high, low, close, 1)  # TR for 1-bar
    atr_n = tr.ewm(alpha=1 / n, adjust=False).mean()

    plus_di = (pd.Series(plus_dm, index=high.index).ewm(alpha=1 / n, adjust=False).mean() / atr_n) * 100.0
    minus_di = (pd.Series(minus_dm, index=high.index).ewm(alpha=1 / n, adjust=False).mean() / atr_n) * 100.0

    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)).fillna(0.0) * 100.0
    adx = dx.ewm(alpha=1 / n, adjust=False).mean()
    return adx


# ───────────────────────────────────────────────────────────────────────────────
# Heuristic regime → window/ADX suggestion
# ───────────────────────────────────────────────────────────────────────────────

def _sanitize_symbol(symbol: str) -> str:
    return symbol.replace("/", "-")


def _clip_windows(total_bars: int, train: int, test: int, step: int) -> SuggestedParams:
    # leave a tiny tail; enforce minima
    usable = max(50, total_bars - 10)
    train = max(120, min(train, usable))
    test  = max( 50, min(test,  usable - 20))
    step  = max( 25, min(step,  max(25, test // 2)))
    return train, test, step


def suggest_params_from_df(df: pd.DataFrame, interval: str) -> SuggestedParams:
    """
    Inspect recent OHLCV to propose walk-forward windows and ADX thresholds.

    Heuristics:
      • Use 90-bar volatility percentile to tier windows.
      • If ADX(14) > 25 → 'trending' → slightly higher ADX threshold.
      • Interval granularity nudges: lower TFs use smaller windows.
    """
    if df is None or df.empty:
        # conservative defaults
        return SuggestedParams(wf_train=600, wf_test=240, wf_step=120, adx_th=15.0, adx_len=14)

    close = df["close"].astype(float)
    high  = df["high"].astype(float)
    low   = df["low"].astype(float)

    # recent realized volatility
    ret = close.pct_change()
    vol_lookback = 90
    rv = ret.rolling(vol_lookback).std().iloc[-1]
    if not np.isfinite(rv) or rv <= 0:
        rv = 0.01  # fallback

    # trend strength
    adx_len = 14
    adx_series = _adx(high, low, close, n=adx_len)
    last_adx = float(adx_series.iloc[-1]) if len(adx_series) else 15.0

    # interval nudges
    interval = (interval or "").lower().strip()
    is_fast = interval in {"1m", "3m", "5m", "15m"}
    is_mid  = interval in {"30m", "1h", "2h"}
    # is_slow = everything else

    # baseline windows by vol tier
    # (vol numbers are empirical; adjust freely later)
    if rv < 0.004:   # very low vol
        base = (900, 300, 150)
    elif rv < 0.008: # low-mid
        base = (700, 260, 120)
    elif rv < 0.015: # mid
        base = (500, 200, 100)
    else:            # high vol
        base = (300, 150,  60)

    # interval nudges
    trn, tst, stp = base
    if is_fast:
        trn, tst, stp = int(trn * 0.75), int(tst * 0.75), int(stp * 0.75)
    elif is_mid:
        trn, tst, stp = int(trn * 0.90), int(tst * 0.90), int(stp * 0.90)

    # ADX threshold suggestion
    if last_adx >= 25:
        adx_th = 18.0
    elif last_adx >= 20:
        adx_th = 15.0
    else:
        adx_th = 12.0

    # clip against available data
    trn, tst, stp = _clip_windows(len(df), trn, tst, stp)

    return SuggestedParams(
        wf_train=int(trn),
        wf_test=int(tst),
        wf_step=int(stp),
        adx_th=float(adx_th),
        adx_len=int(adx_len),
    )


# ───────────────────────────────────────────────────────────────────────────────
# Persistence helpers
# ───────────────────────────────────────────────────────────────────────────────

def _params_path(symbol: str, interval: str, folder: Optional[Path] = None) -> Path:
    folder = folder or Path(".")
    fname  = f"params_{_sanitize_symbol(symbol)}_{interval}.json"
    return folder / fname


def persist_params(symbol: str, interval: str, params: Dict, folder: Optional[Path] = None) -> Path:
    """
    Save selected parameters to params_{symbol}_{interval}.json
    Keys expected by brain.py when reloading:
      wf_train, wf_test, wf_step, adx_threshold, adx_len
    """
    p = _params_path(symbol, interval, folder)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(params)
    # ensure canonical keys exist
    payload.setdefault("wf_train",      params.get("wf_train"))
    payload.setdefault("wf_test",       params.get("wf_test"))
    payload.setdefault("wf_step",       params.get("wf_step"))
    payload.setdefault("adx_threshold", params.get("adx_threshold") or params.get("adx_th"))
    payload.setdefault("adx_len",       params.get("adx_len", 14))
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return p


def load_persisted(symbol: str, interval: str, folder: Optional[Path] = None) -> Optional[Dict]:
    """Return dict of persisted params if present; else None."""
    p = _params_path(symbol, interval, folder)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        # sanity check minimal keys
        if not {"wf_train", "wf_test", "wf_step"}.issubset(set(data.keys())):
            return None
        return data
    except Exception:
        return None

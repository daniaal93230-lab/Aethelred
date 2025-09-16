# bot/ml.py
"""
Lightweight ML helpers for Aethelred.

Exports:
    - train_save_model(df, model_path, horizon=1)
    - predict_last_proba(df, model_path, horizon=1)

Design:
    * Feature engineering kept dependency-light (pandas/numpy only).
    * Model: StandardScaler + LogisticRegression (probability outputs).
    * Target: next-bar (or next H bars) direction: 1 if future return > 0 else 0.
"""

from __future__ import annotations

import time
from typing import Tuple, List, Dict

import numpy as np
import pandas as pd

from joblib import dump, load
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression


# ───────────────────────────────────────────────────────────────────────────────
# TA helpers (no external TA libs)
# ───────────────────────────────────────────────────────────────────────────────

def _ema(x: pd.Series, span: int) -> pd.Series:
    return x.ewm(span=span, adjust=False).mean()

def _rsi(x: pd.Series, n: int = 14) -> pd.Series:
    delta = x.diff()
    up = delta.clip(lower=0.0)
    down = -delta.clip(upper=0.0)
    roll_up = up.rolling(n, min_periods=n).mean()
    roll_down = down.rolling(n, min_periods=n).mean()
    rs = roll_up / (roll_down.replace(0.0, np.nan))
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50.0)

def _atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    pc = close.shift(1)
    tr = pd.concat([(high - low).abs(), (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=n).mean()

def _adx(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    up_move = high.diff()
    dn_move = -low.diff()

    plus_dm = np.where((up_move > dn_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((dn_move > up_move) & (dn_move > 0), dn_move, 0.0)

    tr1 = _atr(high, low, close, n=1)  # true range (1)
    atr_n = tr1.ewm(alpha=1 / n, adjust=False).mean()

    plus_di = (pd.Series(plus_dm, index=high.index).ewm(alpha=1 / n, adjust=False).mean() / atr_n) * 100.0
    minus_di = (pd.Series(minus_dm, index=high.index).ewm(alpha=1 / n, adjust=False).mean() / atr_n) * 100.0

    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)).fillna(0.0) * 100.0
    adx = dx.ewm(alpha=1 / n, adjust=False).mean()
    return adx


# ───────────────────────────────────────────────────────────────────────────────
# Feature engineering
# ───────────────────────────────────────────────────────────────────────────────

def _donch_pos(close: pd.Series, n: int = 20) -> pd.Series:
    hi = close.rolling(n, min_periods=n).max()
    lo = close.rolling(n, min_periods=n).min()
    width = (hi - lo).replace(0, np.nan)
    pos = (close - lo) / width
    return pos.clip(0, 1).fillna(0.5)

def _build_features(df: pd.DataFrame, horizon: int = 1) -> Tuple[pd.DataFrame, pd.Series, List[str]]:
    """
    Returns:
        X (DataFrame), y (Series), feature_names (list)
    """

    # Cast & sanity
    close = df["close"].astype(float)
    high  = df["high"].astype(float)
    low   = df["low"].astype(float)

    # Returns / momentum
    ret1 = close.pct_change(1)
    ret3 = close.pct_change(3)
    ret6 = close.pct_change(6)
    roc5  = close.pct_change(5)
    roc10 = close.pct_change(10)

    # Trend state
    ema12 = _ema(close, 12)
    ema26 = _ema(close, 26)
    ema_ratio = (ema12 / ema26) - 1.0

    # Oscillator / vol
    rsi14 = _rsi(close, 14)
    vol20 = ret1.rolling(20, min_periods=20).std()

    # Range/Trend strength
    atr14 = _atr(high, low, close, 14) / close
    adx14 = _adx(high, low, close, 14)

    # Position within range
    donch_pos20 = _donch_pos(close, 20)

    # Feature frame
    feats: Dict[str, pd.Series] = dict(
        ret1=ret1, ret3=ret3, ret6=ret6,
        roc5=roc5, roc10=roc10,
        ema_ratio=ema_ratio,
        rsi14=rsi14,
        vol20=vol20,
        atr14=atr14,
        adx14=adx14,
        donch_pos20=donch_pos20,
    )
    X = pd.DataFrame(feats, index=df.index)

    # Target: future direction over `horizon`
    fut_ret = close.shift(-horizon) / close - 1.0
    y = (fut_ret > 0).astype(int)

    # Clean
    X = X.replace([np.inf, -np.inf], np.nan)
    X = X.ffill().bfill()
    valid = np.isfinite(X).all(axis=1) & np.isfinite(y)
    X = X.loc[valid]
    y = y.loc[valid]

    # Drop initial warmup where we still might have NaNs
    X = X.iloc[50:]
    y = y.loc[X.index]

    return X, y, list(X.columns)


# ───────────────────────────────────────────────────────────────────────────────
# Public API
# ───────────────────────────────────────────────────────────────────────────────

def train_save_model(df: pd.DataFrame, model_path: str, horizon: int = 1) -> str:
    """
    Train a simple directional classifier and save it with joblib.
    The artifact stores: pipeline, features, horizon, created_at.
    """
    if df is None or df.empty or len(df) < 200:
        raise ValueError("Not enough data to train ML model (need at least ~200 rows).")

    X, y, feats = _build_features(df, horizon=horizon)
    if len(X) < 150 or y.nunique() < 2:
        raise ValueError("Insufficient usable rows or only one class in target after feature prep.")

    # Chronological split (last 10% as validation for quick sanity)
    split = int(len(X) * 0.9)
    X_tr, y_tr = X.iloc[:split], y.iloc[:split]
    X_va, y_va = X.iloc[split:], y.iloc[split:]

    pipe = Pipeline(steps=[
        ("scaler", StandardScaler(with_mean=True, with_std=True)),
        ("clf", LogisticRegression(
            solver="liblinear",
            class_weight="balanced",
            max_iter=200,
            random_state=42,
        )),
    ])

    pipe.fit(X_tr.values, y_tr.values)

    # Simple validation accuracy (optional; won’t break anything if empty)
    acc = None
    try:
        acc = float((pipe.predict(X_va.values) == y_va.values).mean()) if len(X_va) else None
    except Exception:
        acc = None

    artifact = dict(
        pipeline=pipe,
        features=feats,
        horizon=int(horizon),
        created_at=time.time(),
        val_accuracy=acc,
    )

    # Ensure parent folder exists
    from pathlib import Path
    p = Path(model_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    dump(artifact, p)
    return str(p)


def predict_last_proba(df: pd.DataFrame, model_path: str, horizon: int = 1) -> float:
    """
    Load a saved model and return P(up) for the last row of features.
    If horizon mismatches the artifact's horizon, we still compute with requested `horizon`
    to avoid surprises, but logins are kept simple here.
    """
    art = load(model_path)  # dict as saved above
    pipe = art["pipeline"]
    feats_saved = art.get("features", [])
    # horizon_saved = art.get("horizon", horizon)  # not strictly needed

    X_full, _, feat_names_now = _build_features(df, horizon=horizon)
    if X_full.empty:
        return 0.5  # neutral if we cannot compute features

    # Align columns to what the model expects
    X_last = X_full.iloc[[-1]].copy()
    for f in feats_saved:
        if f not in X_last.columns:
            X_last[f] = 0.0  # safe default if feature was missing
    X_last = X_last[feats_saved]

    proba = pipe.predict_proba(X_last.values)[0, 1]  # P(y=1)
    return float(proba)


__all__ = ["train_save_model", "predict_last_proba"]

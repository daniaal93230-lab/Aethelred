import pickle
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

FEATURE_COLS = ["ret_1", "ret_3", "ret_6", "ret_12", "rsi_14", "atr_norm"]

def _features_from_df(df: pd.DataFrame, horizon: int = 1) -> Tuple[pd.DataFrame, pd.Series]:
    """
    Build a minimal feature set from OHLCV dataframe for a binary "next bar up" classifier.
    Expects at least columns: close, high, low.
    """
    close = df["close"].astype(float)
    ret = close.pct_change()
    feats = pd.DataFrame({
        "ret_1": ret,
        "ret_3": close.pct_change(3),
        "ret_6": close.pct_change(6),
        "ret_12": close.pct_change(12),
    })

    # RSI(14)
    delta = close.diff()
    up = delta.clip(lower=0).rolling(14).mean()
    down = (-delta.clip(upper=0)).rolling(14).mean().replace(0.0, np.nan)
    rs = up / down
    feats["rsi_14"] = 100 - (100 / (1 + rs))

    # ATR(14) normalized by price
    tr1 = (df["high"] - df["low"]).abs()
    tr2 = (df["high"] - close.shift()).abs()
    tr3 = (df["low"] - close.shift()).abs()
    atr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(14).mean()
    feats["atr_norm"] = (atr / close)

    # target: next-bar up within horizon
    y = (close.shift(-horizon) > close).astype(float)

    # clean
    feats = feats.ffill().bfill()
    feats = feats.replace([np.inf, -np.inf], np.nan).ffill().bfill()

    mask = y.notna() & feats.notna().all(axis=1)
    feats = feats.loc[mask]
    y = y.loc[mask]
    return feats, y

def ml_model_path(symbol: str, interval: str, override: Optional[str] = None) -> Path:
    """
    Build a consistent path for a symbol/interval ML model.
    """
    if override:
        return Path(override)
    fname = f"{symbol.replace('/', '_')}_{interval}_lin.pkl"
    return Path("ml_models") / fname

def train_save_model(df: pd.DataFrame, model_path: str, horizon: int = 1) -> None:
    """
    Train a simple logistic regression classifier and save (scaler + model).
    """
    X, y = _features_from_df(df, horizon)
    if X.empty or y.empty:
        raise RuntimeError("Not enough data to train the ML model.")

    scaler = StandardScaler()
    Xs = scaler.fit_transform(X.values)

    # time-ordered split (no shuffle)
    Xtr, Xte, ytr, yte = train_test_split(Xs, y.values, test_size=0.2, random_state=42, shuffle=False)

    model = LogisticRegression(max_iter=1000)
    model.fit(Xtr, ytr)

    Path(model_path).parent.mkdir(parents=True, exist_ok=True)
    with open(Path(model_path), "wb") as f:
        pickle.dump({"scaler": scaler, "model": model, "features": list(X.columns)}, f)

def predict_last_proba(model_path: str, df: pd.DataFrame, horizon: int = 1) -> float:
    """
    Return probability (0..1) that the next `horizon` bar is up.
    """
    with open(Path(model_path), "rb") as f:
        bundle = pickle.load(f)

    X, _ = _features_from_df(df, horizon)
    if X.empty:
        return 0.5

    scaler = bundle["scaler"]
    model = bundle["model"]

    Xs = scaler.transform(X.values[-1:].astype(float))
    proba = float(model.predict_proba(Xs)[0, 1])
    return proba

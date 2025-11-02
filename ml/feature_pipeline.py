from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Tuple, Dict, Any
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class FeatureConfig:
    return_windows: Tuple[int, ...] = (1, 3, 6, 12)
    atr_window: int = 14
    vol_window: int = 30
    include_time_of_day: bool = True


def _true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    prev_close = np.concatenate(([close[0]], close[:-1]))
    tr1 = high - low
    tr2 = np.abs(high - prev_close)
    tr3 = np.abs(low - prev_close)
    return np.maximum(tr1, np.maximum(tr2, tr3))


def _time_cyc_features(ts: pd.Series) -> pd.DataFrame:
    # ts is timezone-aware or naive unix seconds
    dt = pd.to_datetime(ts, unit="s", utc=True, errors="coerce")
    hour = dt.dt.hour.fillna(0).astype(int)
    minute = dt.dt.minute.fillna(0).astype(int)
    tod = hour + minute / 60.0
    rad = 2.0 * math.pi * (tod / 24.0)
    return pd.DataFrame(
        {
            "tod_sin": np.sin(rad),
            "tod_cos": np.cos(rad),
        },
        index=ts.index,
    )


def build_features(
    candles: pd.DataFrame,
    cfg: FeatureConfig | None = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Build deterministic features from OHLCV candles.
    Expected columns: ['ts','open','high','low','close','volume'] with ts in seconds.
    Returns X (features) and meta with applied config.
    """
    cfg = cfg or FeatureConfig()
    required = {"ts", "open", "high", "low", "close"}
    missing = required.difference(set(candles.columns))
    if missing:
        raise ValueError(f"build_features: missing columns {sorted(missing)}")

    df = candles.sort_values("ts").reset_index(drop=True).copy()
    close = df["close"].astype(float).to_numpy()
    high = df["high"].astype(float).to_numpy()
    low = df["low"].astype(float).to_numpy()

    feats = {}
    # Recent returns (log returns over windows)
    price = pd.Series(close)
    # replace zero prices with NaN then forward/back fill to avoid -inf from log(0)
    logp = np.log(price.replace(0, np.nan)).ffill().bfill()
    for w in cfg.return_windows:
        feats[f"ret_l{w}"] = (logp - logp.shift(w)).fillna(0.0).to_numpy()

    # ATR-like normalized by price
    tr = _true_range(high, low, close)
    atr = pd.Series(tr).rolling(cfg.atr_window, min_periods=1).mean().to_numpy()
    feats["atr_norm"] = np.divide(atr, np.maximum(close, 1e-9))

    # Rolling volatility of log returns
    ret1 = np.diff(logp, prepend=logp.iloc[0])
    # use ddof=0 so that a single-sample window yields 0.0 (not NaN)
    vol = pd.Series(ret1).rolling(cfg.vol_window, min_periods=1).std(ddof=0).to_numpy()
    feats["vol_l30"] = vol

    # Regime flags: simple fast vs slow momentum
    fast = logp.rolling(10, min_periods=1).mean()
    slow = logp.rolling(50, min_periods=1).mean()
    regime_up = (fast > slow).astype(float).to_numpy()
    feats["regime_up"] = regime_up

    X = pd.DataFrame(feats)

    if cfg.include_time_of_day:
        X = pd.concat([X, _time_cyc_features(df["ts"])], axis=1)

    # Scale features
    # Fit scaler but guard against zero-variance features which produce scale_ == 0
    scaler = StandardScaler()
    scaler.fit(X.values)
    # Protect against division by zero for constant columns by treating zero scale as 1.0
    used_scale = np.where(scaler.scale_ == 0.0, 1.0, scaler.scale_)
    X_scaled_arr = (X.values - scaler.mean_) / used_scale
    X_scaled = pd.DataFrame(X_scaled_arr, columns=X.columns, index=X.index)

    meta = {
        "feature_config": {
            "return_windows": list(cfg.return_windows),
            "atr_window": cfg.atr_window,
            "vol_window": cfg.vol_window,
            "include_time_of_day": cfg.include_time_of_day,
        },
        "scaler_mean": scaler.mean_.tolist(),
        # store the used scale (with zeros replaced) so downstream consumers reproduce transform
        "scaler_scale": used_scale.tolist(),
        "columns": list(X.columns),
    }
    return X_scaled, meta

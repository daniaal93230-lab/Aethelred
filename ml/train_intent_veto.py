from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.utils.class_weight import compute_class_weight
import joblib

from .feature_pipeline import build_features, FeatureConfig
from .labeler import build_labels, LabelConfig
from .metrics import expected_calibration_error, tune_threshold_by_ece


def _ensure_symbol_column(df: pd.DataFrame, sym: str) -> pd.DataFrame:
    if "symbol" not in df.columns:
        df = df.assign(symbol=sym)
    return df


def train_intent_veto(
    signals_csv: Path,
    candles_csv: Path,
    artifacts_dir: Path,
    horizon: int = 12,
    symbol: str = "BTCUSDT",
    random_state: int = 7,
) -> Dict[str, Any]:
    """
    End to end: labels + features + calibrated model + threshold tuning.
    """
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    signals = pd.read_csv(signals_csv)
    candles = pd.read_csv(candles_csv)
    # Normalize ts to seconds unix if needed
    for df in (signals, candles):
        if np.issubdtype(df["ts"].dtype, np.datetime64):
            df["ts"] = pd.to_datetime(df["ts"], utc=True).astype("int64") // 10**9
    signals = _ensure_symbol_column(signals, symbol)
    candles = _ensure_symbol_column(candles, symbol)

    labels = build_labels(
        signals=signals[["ts", "symbol", "side"]],
        candles=candles[["ts", "symbol", "open", "high", "low", "close"]],
        cfg=LabelConfig(horizon=horizon),
    )
    if labels.empty:
        raise RuntimeError("No labels built. Check input files and horizon.")

    # Align candles on label grid for feature building
    merged = labels.merge(
        candles[["ts", "symbol", "open", "high", "low", "close"]],
        on=["ts", "symbol"],
        how="left",
    ).dropna()

    X, feat_meta = build_features(
        candles=merged[["ts", "open", "high", "low", "close"]],
        cfg=FeatureConfig(),
    )
    y = labels.loc[X.index, "y"].to_numpy().astype(int)

    X_train, X_val, y_train, y_val = train_test_split(
        X.to_numpy(),
        y,
        test_size=0.25,
        random_state=random_state,
        stratify=y,
    )

    classes = np.array([0, 1], dtype=int)
    class_weights = compute_class_weight(class_weight="balanced", classes=classes, y=y_train)
    cw = {int(c): float(w) for c, w in zip(classes, class_weights)}

    base = LogisticRegression(
        penalty="l2",
        C=1.0,
        class_weight=cw,
        solver="lbfgs",
        max_iter=200,
        random_state=random_state,
    )
    # Platt scaling via sigmoid calibration
    clf = CalibratedClassifierCV(
        estimator=base, cv=StratifiedKFold(n_splits=5, shuffle=True, random_state=random_state), method="sigmoid"
    )
    clf.fit(X_train, y_train)

    val_prob = clf.predict_proba(X_val)[:, 1]
    ece = expected_calibration_error(y_val, val_prob, n_bins=15)
    thr, thr_metrics = tune_threshold_by_ece(y_val, val_prob)

    model_path = artifacts_dir / "model.pkl"
    meta_path = artifacts_dir / "model_meta.json"
    joblib.dump(clf, model_path)

    meta = {
        "feature_meta": feat_meta,
        "label_meta": {"horizon": horizon, "profit_threshold": 0.0},
        "decision_threshold": float(thr),
        "validation": {
            "ece": float(ece),
            **thr_metrics,
        },
        "random_state": random_state,
        "class_weights": cw,
    }
    meta_path.write_text(json.dumps(meta, indent=2))
    return {
        "model_path": str(model_path),
        "meta_path": str(meta_path),
        "validation": meta["validation"],
        "threshold": meta["decision_threshold"],
    }


def cli():
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--signals", type=Path, required=True, help="CSV with columns ts,symbol,side")
    p.add_argument("--candles", type=Path, required=True, help="CSV with ts,open,high,low,close[,symbol]")
    p.add_argument("--out", type=Path, default=Path("models/intent_veto"))
    p.add_argument("--h", type=int, default=12, help="label horizon in bars")
    p.add_argument("--symbol", type=str, default="BTCUSDT")
    args = p.parse_args()
    res = train_intent_veto(args.signals, args.candles, args.out, horizon=args.h, symbol=args.symbol)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    cli()

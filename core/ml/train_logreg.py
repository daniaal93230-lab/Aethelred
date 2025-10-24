from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
import joblib

from .features import basic_features
from .model_io import MODEL_PATH, FEATURE_NAMES

def make_labels(close: pd.Series, horizon: int = 3, threshold: float = 0.0) -> pd.Series:
    """
    Label 1 if close[t+h] / close[t] - 1 > threshold else 0.
    Default threshold=0 makes it a pure up/down classifier.
    """
    fwd = close.shift(-horizon)
    ret = (fwd / close) - 1.0
    return (ret > threshold).astype(int)

def load_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    # Expect at least a 'close' column.
    if "close" not in df.columns:
        raise ValueError("CSV must contain a 'close' column.")
    return df

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="OHLCV csv with 'close' column")
    ap.add_argument("--horizon", type=int, default=3)
    ap.add_argument("--thr", type=float, default=0.0)
    ap.add_argument("--out", default=str(MODEL_PATH))
    args = ap.parse_args()

    df = load_csv(Path(args.csv))
    feats = basic_features(df)
    labels = make_labels(df["close"].astype(float), horizon=args.horizon, threshold=args.thr)
    data = pd.concat([feats, labels.rename("y")], axis=1).dropna()
    X = data[list(FEATURE_NAMES)].astype(float).values
    y = data["y"].astype(int).values

    pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(max_iter=1000, class_weight="balanced")),
    ])
    pipe.fit(X, y)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe, args.out)
    print(f"saved model -> {args.out}")

if __name__ == "__main__":
    main()

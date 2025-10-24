#!/usr/bin/env python3
# scripts/eval_stop_distance_v1.py
# Evaluate stop_distance_regressor_v1.pkl on a held out slice or k-fold CV splits saved during training.

import argparse
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def ece_regression(y_true, y_pred, n_bins: int = 20):
    order = np.argsort(y_pred)
    y_t = np.asarray(y_true)[order]
    y_p = np.asarray(y_pred)[order]
    idx_bins = np.array_split(np.arange(len(y_p)), n_bins)
    errs = []
    bins = []
    for b in idx_bins:
        if len(b) == 0:
            continue
        pred_mean = y_p[b].mean()
        true_mean = y_t[b].mean()
        bins.append((pred_mean, true_mean))
        errs.append(abs(pred_mean - true_mean) / max(1e-9, true_mean))
    return float(np.mean(errs)) * 100.0, np.array(bins)


def main(models_path: str, eval_csv: str, out_dir: str):
    outp = Path(out_dir)
    outp.mkdir(parents=True, exist_ok=True)

    pkg = joblib.load(models_path)
    model = pkg["sk_model"]
    calib = pkg["calibrator"]
    cols = pkg["feature_cols"]

    df = pd.read_csv(eval_csv)
    if not set(["y", *cols]).issubset(df.columns):
        raise SystemExit(f"Eval CSV must have columns: y and features {cols[:5]}...")

    X = df[cols].values.astype(float)
    y = df["y"].values.astype(float)

    raw = model.predict(X)
    yhat = calib.transform(raw)

    mae = float(np.mean(np.abs(yhat - y)))
    medae = float(np.median(np.abs(yhat - y)))
    ece_pct, bins = ece_regression(y, yhat, n_bins=20)
    r2 = float(1.0 - np.sum((yhat - y) ** 2) / np.sum((y - y.mean()) ** 2))

    metrics = {
        "mae_atr": mae,
        "medae_atr": medae,
        "ece_pct": float(ece_pct),
        "r2": r2,
        "n": int(len(y)),
    }
    print(metrics)

    pd.DataFrame([metrics]).to_csv(outp / "stop_distance_v1_eval_summary.csv", index=False)

    # save calibration plot
    fig = plt.figure(figsize=(6, 5))
    plt.plot(bins[:, 0], bins[:, 1], marker="o", label="bins")
    lim_min = float(min(bins.min(), 0.0))
    lim_max = float(max(bins.max(), 1.0))
    plt.plot([lim_min, lim_max], [lim_min, lim_max], "--", label="perfect")
    plt.xlabel("Predicted ATR distance")
    plt.ylabel("Observed ATR distance")
    plt.title("Calibration - stop_distance_regressor_v1")
    plt.legend()
    fig.tight_layout()
    fig.savefig(outp / "stop_distance_v1_calibration.png", dpi=120)
    plt.close(fig)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/stop_distance_regressor_v1.pkl")
    ap.add_argument("--eval_csv", required=True, help="CSV with columns: y plus model feature columns")
    ap.add_argument("--out", default="reports")
    args = ap.parse_args()
    main(args.model, args.eval_csv, args.out)

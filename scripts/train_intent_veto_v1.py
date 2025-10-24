#!/usr/bin/env python3
# Trains a calibrated classifier that predicts entry quality to veto bad trades.
# Target: label=1 if trade would have yielded profit within horizon after fees+slippage, else 0.

import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import roc_auc_score, brier_score_loss
from sklearn.model_selection import TimeSeriesSplit
from joblib import dump


def atr(high, low, close, n=14):
    tr = pd.concat(
        [
            (high - low),
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(n, min_periods=n).mean()


def make_features(df):
    o, h, l, c, v = [df[k].astype(float) for k in ["open", "high", "low", "close", "volume"]]
    f = pd.DataFrame(index=df.index)
    f["atr14"] = atr(h, l, c, 14)
    f["atr28"] = atr(h, l, c, 28)
    f["ret1"] = c.pct_change()
    f["ret5"] = c.pct_change(5)
    f["std20"] = c.pct_change().rolling(20).std()
    hh = h.rolling(20).max()
    ll = l.rolling(20).min()
    f["pos_dc20"] = ((c - ll) / (hh - ll + 1e-9)).clip(0, 1)
    f["ema20slope"] = c.ewm(span=20, adjust=False, min_periods=20).mean().pct_change()
    f["ema50slope"] = c.ewm(span=50, adjust=False, min_periods=50).mean().pct_change()
    f["volz20"] = ((v - v.rolling(20).mean()) / (v.rolling(20).std() + 1e-9)).clip(-5, 5)
    if isinstance(f.index, pd.DatetimeIndex):
        tod = f.index.hour + f.index.minute / 60.0
        f["tod_sin"] = np.sin(2 * np.pi * tod / 24.0)
        f["tod_cos"] = np.cos(2 * np.pi * tod / 24.0)
        f["dow_sin"] = np.sin(2 * np.pi * f.index.dayofweek / 7.0)
        f["dow_cos"] = np.cos(2 * np.pi * f.index.dayofweek / 7.0)
    return f


def join_and_label(decisions_csv, trades_csv, ohlcv_parquet, horizon_bars=20, fee_bps=6, slip_bps=2):
    dec = pd.read_csv(decisions_csv, parse_dates=["ts"])
    trd = pd.read_csv(trades_csv, parse_dates=["ts"])
    bars = pd.read_parquet(ohlcv_parquet)
    bars["ts"] = pd.to_datetime(bars["ts"])
    bars = bars.set_index("ts")
    # Executed entries only
    fills = trd[trd["status"].eq("filled")].copy().sort_values("ts")
    dec = dec.sort_values("ts")
    out = []
    for sym, gdec in dec.groupby("symbol"):
        gdec = gdec[gdec["intent"].isin(["buy", "sell"])].copy()
        gfill = fills[fills["symbol"].eq(sym)]
        if gfill.empty or gdec.empty:
            continue
        j = pd.merge_asof(
            gdec,
            gfill,
            on="ts",
            by="symbol",
            direction="forward",
            tolerance=pd.Timedelta("10m"),
            suffixes=("_d", "_t"),
        )
        j = j.dropna(subset=["price"])
        sym_bars = bars[bars["symbol"].eq(sym)] if "symbol" in bars.columns else bars
        feats = make_features(sym_bars)
        atr14 = feats["atr14"]
        for _, r in j.iterrows():
            t = r["ts"]
            if t not in feats.index:
                idx = feats.index.searchsorted(t)
                if idx >= len(feats):
                    continue
                t = feats.index[idx]
            idx0 = feats.index.get_loc(t)
            idx1 = min(idx0 + horizon_bars, len(feats) - 1)
            highs = sym_bars["high"].iloc[idx0 : idx1 + 1]
            lows = sym_bars["low"].iloc[idx0 : idx1 + 1]
            entry = float(r["price"])
            side = 1.0 if r["side"] == "buy" else -1.0
            # simple horizon PnL proxy after fees+slippage
            fee = entry * (fee_bps + slip_bps) / 10000.0
            best = float(highs.max()) if side > 0 else float(lows.min())
            pnl = (best - entry) * side - fee
            y = 1 if pnl > 0 else 0
            row = feats.loc[t].to_dict()
            row.update(
                {
                    "symbol": sym,
                    "ts": r["ts"],
                    "side_sign": side,
                    "atr_entry": float(atr14.loc[t]) if np.isfinite(atr14.loc[t]) else np.nan,
                    "y": y,
                }
            )
            out.append(row)
    df = pd.DataFrame(out).replace([np.inf, -np.inf], np.nan).dropna()
    return df


def main(decisions, trades, ohlcv, models_dir, reports_dir, horizon, save_joined=None):
    df = join_and_label(decisions, trades, ohlcv, horizon_bars=horizon)
    if save_joined:
        Path(reports_dir).mkdir(parents=True, exist_ok=True)
        df.to_csv(Path(reports_dir) / "intent_veto_joined.csv", index=False)
    feature_cols = [c for c in df.columns if c not in ["y", "symbol", "ts"]]
    X = df[feature_cols].values.astype(float)
    y = df["y"].values.astype(int)
    tscv = TimeSeriesSplit(n_splits=5)
    probs = np.zeros_like(y, dtype=float)
    fold_stats = []
    models = []
    for k, (tr, va) in enumerate(tscv.split(X)):
        clf = HistGradientBoostingClassifier(max_depth=6, learning_rate=0.05, max_leaf_nodes=31, l2_regularization=0.1)
        # Calibrated on validation fold with sigmoid to reduce ECE
        cal = CalibratedClassifierCV(clf, method="sigmoid", cv="prefit")
        clf.fit(X[tr], y[tr])
        cal.fit(X[va], y[va])
        p = cal.predict_proba(X[va])[:, 1]
        probs[va] = p
        auc = roc_auc_score(y[va], p)
        brier = brier_score_loss(y[va], p)
        fold_stats.append({"fold": k, "auroc": float(auc), "brier": float(brier)})
        models.append((clf, cal))
    auroc = roc_auc_score(y, probs)
    brier = brier_score_loss(y, probs)

    # simple ECE proxy
    def ece(y_true, y_prob, bins=20):
        idx = np.argsort(y_prob)
        y_t = y_true[idx]
        y_p = y_prob[idx]
        chunks = np.array_split(np.arange(len(y_p)), bins)
        err = 0.0
        n = 0
        for ch in chunks:
            if len(ch) == 0:
                continue
            err += abs(y_p[ch].mean() - y_t[ch].mean()) * len(ch)
            n += len(ch)
        return float(err / n) * 100.0

    ece_pct = ece(y, probs, bins=20)
    metrics = {"auroc": float(auroc), "brier": float(brier), "ece_pct": float(ece_pct), "n": int(len(y))}
    print(metrics)
    Path(models_dir).mkdir(parents=True, exist_ok=True)
    Path(reports_dir).mkdir(parents=True, exist_ok=True)
    # keep last calibrated model for simplicity
    final_clf, final_cal = models[-1]
    pkg = {
        "clf": final_clf,
        "cal": final_cal,
        "feature_cols": feature_cols,
        "fit_stats": metrics,
        "horizon_bars": horizon,
    }
    dump(pkg, Path(models_dir) / "intent_veto_v1.pkl")
    pd.DataFrame(fold_stats).to_csv(Path(reports_dir) / "intent_veto_v1_folds.csv", index=False)
    pd.DataFrame([metrics]).to_csv(Path(reports_dir) / "intent_veto_v1_summary.csv", index=False)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--decisions", default="exports/decisions.csv")
    ap.add_argument("--trades", default="exports/trades.csv")
    ap.add_argument("--ohlcv", required=True)
    ap.add_argument("--models", default="models")
    ap.add_argument("--reports", default="reports")
    ap.add_argument("--horizon", type=int, default=20)
    ap.add_argument("--save_joined", action="store_true")
    args = ap.parse_args()
    main(args.decisions, args.trades, args.ohlcv, args.models, args.reports, args.horizon, args.save_joined)

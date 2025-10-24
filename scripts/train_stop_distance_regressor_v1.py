#!/usr/bin/env python3
# scripts/train_stop_distance_regressor_v1.py
# Trains a monotone, calibrated regressor for stop distance in ATR units.

import joblib, argparse
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.experimental import enable_hist_gradient_boosting  # noqa
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import TimeSeriesSplit


# ---------- helpers ----------
def atr(high, low, close, n=14):
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=n).mean()


def make_features(df_ohlc: pd.DataFrame) -> pd.DataFrame:
    o, h, l, c, v = [df_ohlc[k].astype(float) for k in ["open", "high", "low", "close", "volume"]]
    f = pd.DataFrame(index=df_ohlc.index)
    f["atr14"] = atr(h, l, c, 14)
    f["atr28"] = atr(h, l, c, 28)
    f["ret1"] = c.pct_change()
    f["ret5"] = c.pct_change(5)
    f["std20"] = c.pct_change().rolling(20).std()
    rng = (h - l).replace(0, np.nan)
    f["rng20"] = rng.rolling(20).mean()

    def _ema(series: pd.Series, n: int) -> pd.Series:
        return c.ewm(span=n, adjust=False, min_periods=n).mean()

    f["ema20slope"] = _ema(c, 20).pct_change()
    f["ema50slope"] = _ema(c, 50).pct_change()
    # price in channel
    hh = h.rolling(20).max()
    ll = l.rolling(20).min()
    f["pos_dc20"] = ((c - ll) / (hh - ll + 1e-9)).clip(0, 1)
    # volume z
    f["volz20"] = ((v - v.rolling(20).mean()) / (v.rolling(20).std() + 1e-9)).clip(-5, 5)
    # cyc time features - optional if index is tz-aware
    if isinstance(f.index, pd.DatetimeIndex):
        tod = f.index.hour + f.index.minute / 60.0
        f["tod_sin"] = np.sin(2 * np.pi * tod / 24.0)
        f["tod_cos"] = np.cos(2 * np.pi * tod / 24.0)
        f["dow_sin"] = np.sin(2 * np.pi * f.index.dayofweek / 7.0)
        f["dow_cos"] = np.cos(2 * np.pi * f.index.dayofweek / 7.0)
    return f


def realized_adverse_excursion(entry_px, side_sign, lows_future):
    # distance against position in absolute price units
    worst = lows_future.min()
    dd = (entry_px - worst) * side_sign  # positive when it goes against you
    return max(0.0, float(dd))


def join_decisions_trades(decisions_csv, trades_csv, ohlcv_parquet, horizon_bars):
    dec = pd.read_csv(decisions_csv, parse_dates=["ts"], infer_datetime_format=True)
    trd = pd.read_csv(trades_csv, parse_dates=["ts"], infer_datetime_format=True)
    ohlc = pd.read_parquet(ohlcv_parquet)  # must contain open,high,low,close,volume, ts
    ohlc = ohlc.set_index(pd.to_datetime(ohlc["ts"]))
    # only rows with executed trades
    fills = trd[trd["status"].eq("filled")].copy()
    # map decision->fill by nearest forward time and same symbol
    fills = fills.sort_values("ts")
    dec = dec.sort_values("ts")
    out = []
    for sym, grp in dec.groupby("symbol"):
        gdec = grp[grp["intent"].isin(["buy", "sell"])].copy()
        gfill = fills[fills["symbol"].eq(sym)]
        if gfill.empty:
            continue
        # naive forward join
        j = pd.merge_asof(
            gdec,
            gfill,
            on="ts",
            by="symbol",
            direction="forward",
            tolerance=pd.Timedelta("10m"),
            suffixes=("_dec", "_tr"),
        )
        j = j.dropna(subset=["price"])
        if j.empty:
            continue
        # compute ATR at entry and features at entry bar
        sym_ohlc = ohlc[ohlc["symbol"].eq(sym)].copy() if "symbol" in ohlc.columns else ohlc.copy()
        f = make_features(sym_ohlc)
        atr14 = f["atr14"]
        for _, row in j.iterrows():
            t = row["ts"]
            # align to bar index
            if t not in f.index:
                idx = f.index.searchsorted(t)
                if idx >= len(f):
                    continue
                t = f.index[idx]
            # future window lows
            idx0 = f.index.get_loc(t)
            idx1 = min(idx0 + horizon_bars, len(f) - 1)
            lows_future = sym_ohlc["low"].iloc[idx0 : idx1 + 1]
            entry_px = float(row["price"])
            side_sign = 1.0 if row["side"] == "buy" else -1.0
            rae_price = realized_adverse_excursion(entry_px, side_sign, lows_future)
            atr_entry = float(atr14.loc[t])
            if not np.isfinite(atr_entry) or atr_entry <= 0:
                continue
            y = rae_price / atr_entry
            X = f.loc[t].to_dict()
            X["atr_entry"] = atr_entry
            X["side_sign"] = side_sign
            X["symbol"] = sym
            X["ts"] = row["ts"]
            out.append({**X, "y": y})
    return pd.DataFrame(out)


def ece_regression(y_true, y_pred, n_bins=20):
    order = np.argsort(y_pred)
    y_t = np.asarray(y_true)[order]
    y_p = np.asarray(y_pred)[order]
    bins = np.array_split(np.arange(len(y_p)), n_bins)
    errs = []
    for b in bins:
        if len(b) == 0:
            continue
        errs.append(abs(y_p[b].mean() - y_t[b].mean()) / max(1e-9, y_t[b].mean()))
    return float(np.mean(errs)) * 100.0  # percent


def main(decisions_csv, trades_csv, ohlcv_parquet, models_dir, reports_dir, horizon_bars=20):
    df = join_decisions_trades(decisions_csv, trades_csv, ohlcv_parquet, horizon_bars)
    df = df.replace([np.inf, -np.inf], np.nan).dropna()
    feature_cols = [c for c in df.columns if c not in ["y", "symbol", "ts"]]
    # monotone: +1 for volatility features
    mono_cols = ["atr14", "atr28", "std20", "rng20"]
    mono_mask = [1 if c in mono_cols else 0 for c in feature_cols]
    X = df[feature_cols].values
    y = df["y"].values

    tscv = TimeSeriesSplit(n_splits=5)
    preds = np.zeros_like(y, dtype=float)
    fold_stats = []
    models = []
    calibrators = []
    for fold, (tr, va) in enumerate(tscv.split(X)):
        Xtr, ytr = X[tr], y[tr]
        Xva, yva = X[va], y[va]
        model = HistGradientBoostingRegressor(
            max_depth=6, learning_rate=0.05, l2_regularization=0.1, max_leaf_nodes=31, monotonic_cst=mono_mask
        )
        model.fit(Xtr, ytr)
        pva = model.predict(Xva)
        # isotonic calibration on prediction-to-actual mapping
        calib = IsotonicRegression(out_of_bounds="clip")
        calib.fit(pva, yva)
        pva_cal = calib.transform(pva)
        preds[va] = pva_cal
        mae = np.mean(np.abs(pva_cal - yva))
        medae = np.median(np.abs(pva_cal - yva))
        ece = ece_regression(yva, pva_cal, n_bins=15)
        fold_stats.append({"fold": fold, "mae": float(mae), "medae": float(medae), "ece_pct": float(ece)})
        models.append(model)
        calibrators.append(calib)

    mae_full = np.mean(np.abs(preds - y))
    ece_full = ece_regression(y, preds, n_bins=20)
    print({"mae": mae_full, "ece_pct": ece_full})

    models_dir = Path(models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    out = {
        "sk_model": models[-1],  # final fold model
        "calibrator": calibrators[-1],
        "feature_cols": feature_cols,
        "mono_mask": mono_mask,
        "fit_stats": {"mae": float(mae_full), "ece_pct": float(ece_full), "folds": fold_stats},
        "horizon_bars": horizon_bars,
    }
    joblib.dump(out, models_dir / "stop_distance_regressor_v1.pkl")
    pd.DataFrame(fold_stats).to_csv(reports_dir / "stop_distance_v1_eval.csv", index=False)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--decisions", default="exports/decisions.csv")
    ap.add_argument("--trades", default="exports/trades.csv")
    ap.add_argument("--ohlcv", required=True, help="Parquet with OHLCV and ts (and optional symbol)")
    ap.add_argument("--models", default="models")
    ap.add_argument("--reports", default="reports")
    ap.add_argument("--horizon", type=int, default=20)
    ap.add_argument("--save_joined", default=None, help="Path to write joined features+y CSV for later eval")
    args = ap.parse_args()
    # Run join first to optionally emit dataset
    df_join = join_decisions_trades(args.decisions, args.trades, args.ohlcv, args.horizon)
    if args.save_joined:
        outp = Path(args.save_joined)
        outp.parent.mkdir(parents=True, exist_ok=True)
        df_join.to_csv(outp, index=False)
    # Reuse main for training/eval artifacts
    main(args.decisions, args.trades, args.ohlcv, args.models, args.reports, args.horizon)

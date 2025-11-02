from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class LabelConfig:
    horizon: int = 12  # in bars of the candle series provided
    profit_threshold: float = 0.0  # label is 1 if future_return > threshold


def _forward_return(close: pd.Series, horizon: int) -> pd.Series:
    fwd = close.shift(-horizon) / close - 1.0
    return fwd


def build_labels(
    signals: pd.DataFrame,
    candles: pd.DataFrame,
    cfg: LabelConfig | None = None,
) -> pd.DataFrame:
    """
    Join raw strategy signals to future PnL over horizon H.
    signals columns expected: ['ts','symbol','side'] with side in {1,-1}
    candles columns expected: ['ts','symbol','open','high','low','close']
    Returns a frame with ['ts','symbol','side','y'] where y is 0/1 label.
    """
    cfg = cfg or LabelConfig()
    for col in ("ts", "symbol"):
        if col not in signals.columns:
            raise ValueError(f"build_labels: signals missing '{col}'")
        if col not in candles.columns:
            raise ValueError(f"build_labels: candles missing '{col}'")

    # Merge on nearest candle at or after signal ts per symbol
    c = candles.sort_values(["symbol", "ts"]).copy()
    s = signals.sort_values(["symbol", "ts"]).copy()
    # For efficient asof per symbol
    out_rows = []
    for sym, s_grp in s.groupby("symbol"):
        c_grp = c[c["symbol"] == sym]
        if c_grp.empty:
            continue
        merged = pd.merge_asof(
            s_grp.sort_values("ts"),
            c_grp.sort_values("ts"),
            on="ts",
            by="symbol",
            direction="forward",
            tolerance=pd.Timedelta("1h") if np.issubdtype(c_grp["ts"].dtype, np.datetime64) else None,
        )
        merged = merged.dropna(subset=["close"])
        if merged.empty:
            continue
        # compute forward returns on candle grid
        # We need aligned future close. Use candle index after merge to compute forward returns.
        # Re-join to candle grid indices
        tmp = pd.merge(
            merged[["ts", "symbol", "side"]],
            c_grp.reset_index().rename(columns={"index": "c_idx"}),
            on=["ts", "symbol"],
            how="left",
        )
        cg = c_grp.reset_index(drop=True)
        future_idx = (tmp["c_idx"].fillna(-1).astype(int) + cfg.horizon).clip(lower=-1)
        valid = future_idx >= 0
        close_now = cg["close"].reindex(tmp["c_idx"][valid]).to_numpy()
        close_future = cg["close"].reindex(future_idx[valid]).to_numpy()
        fwd_ret = close_future / close_now - 1.0
        # Side-aware return
        side = tmp.loc[valid, "side"].astype(float).to_numpy()
        pnl = side * fwd_ret
        y = (pnl > cfg.profit_threshold).astype(int)
        out = tmp.loc[valid, ["ts", "symbol", "side"]].copy()
        out["y"] = y
        out_rows.append(out)
    if not out_rows:
        return pd.DataFrame(columns=["ts", "symbol", "side", "y"])
    return pd.concat(out_rows, ignore_index=True)

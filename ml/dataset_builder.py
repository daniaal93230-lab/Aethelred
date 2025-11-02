from __future__ import annotations
import os
from dataclasses import dataclass
import pandas as pd
import numpy as np


@dataclass(frozen=True)
class DatasetConfig:
    horizon: int = int(os.getenv("AETHELRED_H", "12"))


def build_signals_outcomes(
    decisions_csv: str,
    trades_csv: str,
    cfg: DatasetConfig | None = None,
) -> pd.DataFrame:
    """
    Create a clean signal↔outcome dataset using executed trades.
    - decisions.csv must contain: ts,symbol,side
    - trades.csv must contain: symbol,entry_ts,exit_ts,entry,exit,side,pnl
    Label = 1 if trade PnL > 0 over horizon H, else 0.
    """
    cfg = cfg or DatasetConfig()
    dec = pd.read_csv(decisions_csv)
    tr = pd.read_csv(trades_csv)

    for col in ("symbol", "side"):
        if col not in tr.columns or col not in dec.columns:
            raise ValueError("Missing required columns in trades/decisions CSV.")

    # Convert timestamps to numeric seconds if datetimes
    for df in (dec, tr):
        if np.issubdtype(df["ts"].dtype, np.datetime64):
            df["ts"] = pd.to_datetime(df["ts"], utc=True).astype("int64") // 10**9
        if "entry_ts" in df.columns:
            df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True).astype("int64") // 10**9
        if "exit_ts" in df.columns:
            df["exit_ts"] = pd.to_datetime(df["exit_ts"], utc=True).astype("int64") // 10**9

    # Align decisions to nearest trade within horizon window
    merged = pd.merge_asof(
        dec.sort_values("ts"),
        tr.sort_values("entry_ts").rename(columns={"entry_ts": "ts"}),
        on="ts",
        by="symbol",
        direction="forward",
        tolerance=cfg.horizon * 60,  # horizon minutes
    ).dropna(subset=["pnl"])

    # Side-aware outcome
    merged["label"] = (merged["pnl"] * merged["side"]) > 0
    merged["label"] = merged["label"].astype(int)

    return merged[["ts", "symbol", "side", "label"]].rename(columns={"label": "y"})

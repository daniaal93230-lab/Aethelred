#!/usr/bin/env python3
import argparse
from pathlib import Path
import pandas as pd


def main(inp, outp, rows, days=None):
    df = pd.read_parquet(inp)
    if "ts" in df.columns:
        df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
        df = df.sort_values(["symbol", "ts"]) if "symbol" in df.columns else df.sort_values("ts")
    if days:
        # take the most recent N days per symbol if possible
        if "ts" in df.columns:
            tmax = df["ts"].max()
            cutoff = tmax - pd.Timedelta(days=days)
            if "symbol" in df.columns:
                df = df.groupby("symbol", group_keys=False).apply(lambda g: g[g["ts"] >= cutoff])
            else:
                df = df[df["ts"] >= cutoff]
    if rows:
        if "symbol" in df.columns:
            df = df.groupby("symbol", group_keys=False).head(max(1, rows // max(1, df["symbol"].nunique())))
        else:
            df = df.head(rows)
    Path(outp).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(outp, index=False)
    print(f"Wrote {len(df)} rows to {outp}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="outp", required=True)
    ap.add_argument("--rows", type=int, default=5000)
    ap.add_argument("--days", type=int, default=None)
    args = ap.parse_args()
    main(args.inp, args.outp, args.rows, args.days)

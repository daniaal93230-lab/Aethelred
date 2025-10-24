#!/usr/bin/env python3
# scripts/export_ohlcv_parquet.py
# Export OHLCV to Parquet with columns: ts, open, high, low, close, volume, symbol

import argparse
import time
from pathlib import Path
import pandas as pd
import ccxt


def fetch_ohlcv_safe(ex, symbol, timeframe, since_ms=None, limit=1000, sleep_s=1.2):
    out = []
    while True:
        batch = ex.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ms, limit=limit)
        if not batch:
            break
        out.extend(batch)
        since_ms = batch[-1][0] + 1
        time.sleep(sleep_s)
        if len(batch) < limit:
            break
    return out


essential_cols = ["ts", "open", "high", "low", "close", "volume", "symbol"]


def main(exchange, symbols, timeframe, outfile, since_iso=None):
    ex = getattr(ccxt, exchange)({"enableRateLimit": True})
    all_frames = []
    for sym in symbols:
        print(f"Fetching {sym} {timeframe}...")
        since_ms = None
        if since_iso:
            since_ms = int(pd.Timestamp(since_iso).timestamp() * 1000)
        data = fetch_ohlcv_safe(ex, sym, timeframe, since_ms=since_ms)
        if not data:
            continue
        df = pd.DataFrame(data, columns=["ts_ms", "open", "high", "low", "close", "volume"])
        df["ts"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True)
        df["symbol"] = sym
        df = df[["ts", "open", "high", "low", "close", "volume", "symbol"]]
        all_frames.append(df)
    if not all_frames:
        raise SystemExit("No data fetched")
    out = pd.concat(all_frames).sort_values(["symbol", "ts"]).reset_index(drop=True)
    Path(outfile).parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(outfile, index=False)
    print(f"Wrote {len(out)} rows to {outfile}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--exchange", default="binance")
    ap.add_argument("--symbols", nargs="+", required=True, help="e.g. BTC/USDT ETH/USDT SOL/USDT")
    ap.add_argument("--timeframe", default="1m")
    ap.add_argument("--outfile", default="data/ohlcv.parquet")
    ap.add_argument("--since", dest="since_iso", default=None, help="ISO start, e.g. 2024-01-01T00:00:00Z")
    args = ap.parse_args()
    main(args.exchange, args.symbols, args.timeframe, args.outfile, args.since_iso)

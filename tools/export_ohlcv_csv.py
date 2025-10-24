from __future__ import annotations
import os, sys, time, csv
from pathlib import Path
from typing import List
import ccxt


def main():
    """
    Export recent OHLCV to CSV with columns: ts, open, high, low, close, volume
    Env/CLI:
      EXCHANGE (default binance), SYMBOL (e.g., BTC/USDT), TIMEFRAME (e.g., 1m), LIMIT (e.g., 2000)
      Usage: python tools/export_ohlcv_csv.py BTC/USDT 1m 5000  (exchange from EXCHANGE env)
    """
    ex_name = os.getenv("EXCHANGE", "binance")
    symbol = sys.argv[1] if len(sys.argv) > 1 else os.getenv("SYMBOL")
    tf = sys.argv[2] if len(sys.argv) > 2 else os.getenv("TIMEFRAME", "1m")
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else int(os.getenv("LIMIT", "5000"))
    if not symbol:
        print(
            "Usage: python tools/export_ohlcv_csv.py SYMBOL [TIMEFRAME] [LIMIT]\n"
            "Example: python tools/export_ohlcv_csv.py ETH/USDT 1m 10000"
        )
        sys.exit(2)

    ex = getattr(ccxt, ex_name)({"enableRateLimit": True})
    out = Path("data") / f"{symbol.replace('/', '_')}_{tf}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)

    # single call (most exchanges cap ~1000–1500); simple pagination loop
    all_rows: List[List] = []
    since = None
    while len(all_rows) < limit:
        batch = ex.fetch_ohlcv(symbol, timeframe=tf, since=since, limit=min(1000, limit - len(all_rows)))
        if not batch:
            break
        all_rows.extend(batch)
        since = batch[-1][0] + 1
        time.sleep(ex.rateLimit / 1000.0)

    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ts", "open", "high", "low", "close", "volume"])
        for ts, o, h, l, c, v in all_rows:
            w.writerow([ts, o, h, l, c, v])
    print(f"Wrote {len(all_rows)} rows -> {out}")


if __name__ == "__main__":
    main()

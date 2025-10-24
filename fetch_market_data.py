# fetch_market_data.py
import time
import math
import requests  # type: ignore[import-untyped]
import pandas as pd

BINANCE_SPOT = "https://api.binance.com/api/v3/klines"

_INTERVAL_MS = {
    "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
    "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000, "6h": 21_600_000, "8h": 28_800_000, "12h": 43_200_000,
    "1d": 86_400_000, "3d": 259_200_000, "1w": 604_800_000, "1M": 2_592_000_000
}

def _norm_symbol(symbol: str) -> str:
    s = symbol.replace("/", "").upper()
    return s

def _to_df(rows):
    if not rows:
        return pd.DataFrame(columns=["timestamp","open","high","low","close","volume"])
    df = pd.DataFrame(rows, columns=[
        "open_time","open","high","low","close","volume",
        "close_time","qav","trades","taker_base","taker_quote","ignore"
    ])
    df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms")
    for c in ("open","high","low","close","volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[["timestamp","open","high","low","close","volume"]]

def fetch_data(symbol: str, interval: str = "1h", limit: int = 1200,
               since: int | None = None,  # ms since epoch
               max_bars: int | None = None,
               pause_ms: int = 250) -> pd.DataFrame:
    """
    If 'since' is None, grabs up to 'limit' bars (single request).
    If 'since' is provided, auto-paginates from 'since' to now (respects Binance 1k limit).
    Optionally stop after 'max_bars'.
    """
    sym = _norm_symbol(symbol)
    iv_ms = _INTERVAL_MS.get(interval)
    if iv_ms is None:
        raise ValueError(f"Unsupported interval: {interval}")

    if since is None:
        url = f"{BINANCE_SPOT}?symbol={sym}&interval={interval}&limit={min(limit,1000)}"
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        return _to_df(resp.json())

    # paginate
    out = []
    start = int(since)
    fetched = 0
    while True:
        url = f"{BINANCE_SPOT}?symbol={sym}&interval={interval}&limit=1000&startTime={start}"
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        chunk = resp.json()
        if not chunk:
            break
        out.extend(chunk)
        fetched += len(chunk)
        # next page starts at last close_time + 1 ms
        next_start = chunk[-1][6] + 1
        if max_bars and fetched >= max_bars:
            break
        # guard loop end
        if next_start <= start:
            break
        start = next_start
        time.sleep(pause_ms / 1000.0)

    df = _to_df(out)
    if max_bars:
        df = df.tail(max_bars)
    return df.reset_index(drop=True)

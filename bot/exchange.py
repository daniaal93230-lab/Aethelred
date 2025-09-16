# bot/exchange.py
from __future__ import annotations

import time
from typing import List, Optional
import ccxt
import pandas as pd

# Built-in Binance alternates (CCXT understands `hostname` for binance)
_BINANCE_HOSTS = [
    "api.binance.com",
    "api1.binance.com",
    "api2.binance.com",
    "api3.binance.com",
    "api4.binance.com",
]

def _tf_to_ms(tf: str) -> int:
    tf = tf.strip().lower()
    num = int("".join(ch for ch in tf if ch.isdigit()))
    unit = "".join(ch for ch in tf if ch.isalpha())
    if unit == "m":
        return num * 60_000
    if unit == "h":
        return num * 3_600_000
    if unit == "d":
        return num * 86_400_000
    # fallback: hours
    return num * 3_600_000

def _create_exchange(exchange_name: str, timeout_ms: int = 30000, proxy: Optional[str] = None, host_idx: int = 0) -> ccxt.Exchange:
    ex_class = getattr(ccxt, exchange_name)
    cfg = {
        "enableRateLimit": True,
        "timeout": timeout_ms,
        "options": {"adjustForTimeDifference": True},
    }
    if proxy:
        cfg["proxy"] = proxy
    if exchange_name.lower() == "binance":
        cfg["hostname"] = _BINANCE_HOSTS[host_idx % len(_BINANCE_HOSTS)]
    return ex_class(cfg)

def _retry(fn, retries: int = 4, base_sleep: float = 1.25):
    last = None
    for i in range(retries):
        try:
            return fn()
        except Exception as e:
            last = e
            time.sleep(base_sleep * (i + 1))
    raise last

def fetch_ohlcv_paginated(
    exchange_name: str,
    symbol: str,
    timeframe: str,
    limit: int = 1500,
    page_size: int = 1000,
    timeout_ms: int = 30000,
    proxy: Optional[str] = None,
) -> pd.DataFrame:
    """
    Robust OHLCV fetch with retries and (for Binance) rotating `hostname`.
    Returns a DataFrame indexed by UTC ts with columns: open, high, low, close, volume
    """
    # 1) create exchange (try alt hosts for binance)
    ex: Optional[ccxt.Exchange] = None
    last_err = None
    host_range = range(len(_BINANCE_HOSTS)) if exchange_name.lower() == "binance" else range(1)
    for host_idx in host_range:
        try:
            ex = _create_exchange(exchange_name, timeout_ms=timeout_ms, proxy=proxy, host_idx=host_idx)
            _retry(lambda: ex.load_markets(), retries=4, base_sleep=1.5)
            break
        except Exception as e:
            last_err = e
            ex = None
    if ex is None:
        raise last_err or RuntimeError("Failed to initialize exchange client")

    # 2) paginate
    out: List[List[float]] = []
    since = None
    tf_ms = _tf_to_ms(timeframe)
    remaining = max(1, limit)

    while remaining > 0:
        wanted = min(page_size, remaining)

        def _fetch():
            return ex.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=wanted)

        # try fetch with retries
        batch = _retry(_fetch, retries=4, base_sleep=1.5)

        if not batch:
            break

        out += batch
        remaining -= len(batch)
        since = batch[-1][0] + tf_ms

        # Some exchanges cap per-call results (e.g., 100/200). Keep paginating until we hit our overall limit or the exchange returns empty.
        if len(batch) == 0:
            break

        # be gentle with rate limits
        time.sleep((getattr(ex, "rateLimit", 200)) / 1000.0)

    if not out:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    df = pd.DataFrame(out, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.rename(columns={"timestamp": "ts"}).set_index("ts")
    return df

# data_fetch.py
"""
Module for fetching historical OHLCV data from exchanges and time frame utilities.
Uses ccxt for exchange data retrieval.
"""

import time
from typing import List
import pandas as pd

# Mapping of timeframe strings to milliseconds
TF_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
    "3d": 259_200_000,
    "1w": 604_800_000,
}

def tf_to_ms(tf: str) -> int:
    """Convert a timeframe string (e.g. "1m", "1h", "1d") to its duration in milliseconds."""
    if tf not in TF_MS:
        raise ValueError(f"Unsupported timeframe: {tf}")
    return TF_MS[tf]

def now_ms() -> int:
    """Return current timestamp in milliseconds."""
    return int(time.time() * 1000)

def floor_to_tf_ms(ts_ms: int, tf_ms: int) -> int:
    """Floor a timestamp (in ms) down to the nearest timeframe interval (in ms)."""
    return (ts_ms // tf_ms) * tf_ms

def expected_last_closed_ms(tf: str) -> int:
    """Return the timestamp (ms) of the most recent fully closed candle for the given timeframe."""
    tf_ms = tf_to_ms(tf)
    return floor_to_tf_ms(now_ms(), tf_ms)

def fetch_ohlcv_paginated(exchange, symbol: str, timeframe: str, total_limit: int) -> List[List[float]]:
    """
    Fetch up to `total_limit` OHLCV candlesticks from the exchange for a given symbol and timeframe.
    Uses multiple requests if necessary to page through the data.
    Returns a list of [timestamp, open, high, low, close, volume] entries, including only closed bars up to the latest complete interval.
    
    Parameters:
        exchange: ccxt exchange instance (with markets loaded or will be loaded).
        symbol (str): Market symbol (e.g. "BTC/USDT").
        timeframe (str): Timeframe identifier (must be supported by exchange, e.g. "4h", "1d").
        total_limit (int): Total number of data points to retrieve.
    """
    # Ensure exchange markets are loaded (for symbol and method availability)
    if not getattr(exchange, "markets", None):
        exchange.load_markets()
    tf_ms = tf_to_ms(timeframe)
    target_last = expected_last_closed_ms(timeframe)  # Only fetch up to last closed bar
    
    # Determine maximum batch size per request (if exchange has specific limit for OHLCV fetch)
    per_request = 1000  # default conservative max
    if hasattr(exchange, "options") and isinstance(exchange.options, dict):
        maybe = exchange.options.get("OHLCVLimit") or exchange.options.get("fetchOHLCVLimit")
        if isinstance(maybe, int) and maybe > 0:
            per_request = min(per_request, maybe)
    
    earliest_needed = target_last - (total_limit * tf_ms)
    result: List[List[float]] = []
    since = earliest_needed
    
    # Loop to fetch data in batches until we have the requested number of candles or run out of data
    while True:
        remaining = total_limit - len(result)
        if remaining <= 0:
            break
        req_limit = min(per_request, remaining)
        batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=req_limit)
        if not batch:
            break
        # Filter out any candle that is beyond the target_last (not fully closed in our timeframe)
        batch = [row for row in batch if row[0] <= target_last]
        if not batch:
            break
        # Remove any overlapping or duplicate data points (in case of overlapping fetch windows)
        if result:
            last_ts = result[-1][0]
            batch = [row for row in batch if row[0] > last_ts]
        if not batch:
            break
        # Append the batch to results
        result.extend(batch)
        # Move the "since" pointer to the next candle after the last fetched to avoid overlap
        last_batch_ts = batch[-1][0]
        next_since = last_batch_ts + tf_ms
        if next_since <= since:
            # Safety check to avoid infinite loop if exchange returns same last timestamp
            break
        since = next_since
        # Respect exchange rate limit to avoid hitting API too quickly
        if hasattr(exchange, "rateLimit"):
            time.sleep(max(0.0, exchange.rateLimit / 1000.0))
        else:
            time.sleep(0.2)
    # Trim result if we got more than needed (should not typically happen unless duplicates occurred)
    if len(result) > total_limit:
        result = result[-total_limit:]
    return result

def candles_to_df(candles: List[List[float]]) -> pd.DataFrame:
    """Convert a list of OHLCV candles to a pandas DataFrame with timestamp index (UTC)."""
    if not candles:
        # Return an empty DataFrame with the expected columns if no data.
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"]).set_index("timestamp")
    df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.set_index("timestamp").sort_index()
    return df

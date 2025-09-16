try:
    from core.data_fetch import *  # re-export
except ImportError:
    # Minimal fallback
    import time
    import pandas as pd

    def fetch_ohlcv_paginated(exchange, symbol: str, interval: str, limit: int = 5000):
        return exchange.fetch_ohlcv(symbol, timeframe=interval, limit=limit)

    def candles_to_df(candles):
        cols = ["timestamp","open","high","low","close","volume"]
        df = pd.DataFrame(candles, columns=cols)
        if df.empty:
            df.index = pd.to_datetime([])
            return df
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df.set_index("timestamp", inplace=True)
        return df

    def expected_last_closed_ms(interval: str) -> int:
        unit = interval[-1].lower()
        n = int(interval[:-1])
        if unit == "m": length_ms = n * 60_000
        elif unit == "h": length_ms = n * 3_600_000
        elif unit == "d": length_ms = n * 86_400_000
        else: length_ms = 3_600_000
        now_ms = int(time.time() * 1000)
        return (now_ms // length_ms) * length_ms

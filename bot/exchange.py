# bot/exchange.py
from __future__ import annotations

import time, os
from typing import List, Optional, Union, Dict
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
    if last is not None:
        raise last
    raise RuntimeError("retry failed with no exception captured")

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


class Exchange:
    """
    Minimal exchange wrapper used by the engine and tests.
    Provides fetch_ohlcv(symbol, use_live=False) and place_market_order(symbol, side, amount_or_notional).
    """
    def __init__(self, exchange_name: str = "binance", timeframe: str = "15m"):
        self.exchange_name = exchange_name
        self.timeframe = timeframe

    def fetch_ohlcv(self, symbol: str, use_live: bool = False, timeframe: Optional[str] = None, limit: int = 200) -> List[List[Union[int, float]]]:
        tf = timeframe or self.timeframe
        if use_live:
            try:
                df = fetch_ohlcv_paginated(self.exchange_name, symbol, tf, limit=limit)
                if df.empty:
                    return []
                out = []
                for ts, row in df.tail(limit).iterrows():
                    out.append([
                        int(ts.value // 10**6),
                        float(row["open"]),
                        float(row["high"]),
                        float(row["low"]),
                        float(row["close"]),
                        float(row["volume"]),
                    ])
                return out
            except Exception:
                return []
        # mock data: simple rising series
        now = int(time.time() * 1000)
        base = 100.0
        candles: List[List[Union[int, float]]] = []
        for i in range(limit):
            o = base + i * 0.1
            h = o * 1.01
            l = o * 0.99
            c = o
            v = 1.0 + i * 0.01
            candles.append([now - (limit - i) * 60_000, o, h, l, c, v])
        return candles

    def place_market_order(self, symbol: str, side: str, amount_or_notional: float) -> None:
        # No-op for tests; in live use, this would route to the exchange via ccxt
        return None

    # --- Paper / mock account overview for dashboard ---
    def account_overview(self) -> dict:
        """Return a minimal snapshot used by ExecutionEngine.write_account_runtime.
        Since this mock exchange doesn't track positions, we return zero exposure and
        use a synthetic equity placeholder (could be extended to maintain PnL).
        """
        # Prefer last equity snapshot from DB if present; else fallback to starting cash
        equity_val = None
        try:
            from db.db_manager import load_last_equity
            equity_val = load_last_equity()
        except Exception:
            equity_val = None
        if equity_val is None or equity_val <= 0:
            try:
                equity_val = float(os.getenv("PAPER_STARTING_CASH", "10000"))
            except Exception:
                equity_val = 10000.0
        cash_val = float(equity_val)
        return {
            "equity": float(equity_val),
            "cash": float(cash_val),
            "exposure_usd": 0.0,
            "positions": [],
        }


class PaperExchange:
    """
    Simple paper exchange that persists cash, positions, and trades in SQLite via db.db_manager.
    Supports buy_notional (USD) and sell_qty, and exposes account_overview with mark-to-market.
    """
    def __init__(self, fees_bps: float = 7.0, slippage_bps: float = 5.0, timeframe: str = "15m", exchange_name: str = "binance"):
        try:
            from db.db_manager import init_db
            init_db()
        except Exception:
            pass
        self.fees_bps = float(os.environ.get("FEES_BPS", fees_bps))
        self.slippage_bps = float(os.environ.get("SLIPPAGE_BPS", slippage_bps))
        # use an internal live/mock exchange for data fetching
        self.timeframe = timeframe
        self._fetch_ex = Exchange(exchange_name=exchange_name, timeframe=timeframe)
        self._last_prices: Dict[str, float] = {}

    def _apply_slippage(self, price: float, side: str) -> float:
        bps = float(self.slippage_bps) / 10000.0
        return float(price) * (1.0 + bps if side.upper() == "BUY" else 1.0 - bps)

    def buy_notional(self, symbol: str, usd: float, last_price: float) -> None:
        from db.db_manager import insert_paper_trade, get_cash, set_cash, upsert_position
        px = self._apply_slippage(last_price, "BUY")
        if px <= 0:
            return
        qty = float(usd) / float(px)
        ts = int(time.time())
        fees = insert_paper_trade(ts, symbol, "BUY", qty, px, self.fees_bps, slippage_bps=self.slippage_bps, run_id=os.getenv("RUN_ID"))
        cash = get_cash()
        set_cash(float(cash) - qty * px - fees)
        upsert_position(symbol, qty, px)

    def sell_qty(self, symbol: str, qty: float, last_price: float) -> None:
        from db.db_manager import insert_paper_trade, get_cash, set_cash, upsert_position
        px = self._apply_slippage(last_price, "SELL")
        ts = int(time.time())
        fees = insert_paper_trade(ts, symbol, "SELL", qty, px, self.fees_bps, slippage_bps=self.slippage_bps, run_id=os.getenv("RUN_ID"))
        cash = get_cash()
        set_cash(float(cash) + float(qty) * px - fees)
        upsert_position(symbol, -float(qty), px)

    def account_overview(self, mid_prices: Optional[Dict[str, float]] = None) -> dict:
        from db.db_manager import mark_to_market, get_positions, get_cash
        prices = mid_prices or {}
        self._last_prices.update(prices)
        # compute MTM and reconstruct richer positions payload
        equity, cash, exposure, positions = mark_to_market(self._last_prices)
        now = time.time()
        pos_list = []
        for s, p in positions.items():
            qty = float(p.get("qty", 0.0))
            if abs(qty) <= 0:
                continue
            avg = float(p.get("avg_price", 0.0))
            mkt = float(self._last_prices.get(s, 0.0))
            side = "long" if qty > 0 else ("short" if qty < 0 else "")
            entry_ts = p.get("entry_ts")
            held = 0.0
            try:
                held = max(0.0, (now - (float(entry_ts) if entry_ts else now)) / 60.0)
            except Exception:
                held = 0.0
            unreal_pct = 0.0 if avg == 0 else ((mkt - avg) / avg) * (1 if qty >= 0 else -1)
            pos_list.append({
                "symbol": s,
                "side": side,
                "qty": qty,
                "avg_price": avg,
                "entry_ts": entry_ts,
                "market_price": mkt,
                "unrealized_pct": float(unreal_pct),
                "holding_mins": float(held),
            })
        # persist equity updated_ts for diagnostics
        try:
            from db.db_manager import _get_conn
            with _get_conn() as _c:
                _c.execute("UPDATE paper_account SET equity=?, updated_ts=strftime('%s','now') WHERE id=1", (float(equity),))
                _c.commit()
        except Exception:
            pass
        return {"ts": now, "equity": float(equity), "cash": float(cash), "exposure_usd": float(exposure), "positions": pos_list}

    def market_close_all(self, mid_prices: Dict[str, float]) -> dict:
        from db.db_manager import get_positions
        out = []
        for s, p in get_positions().items():
            qty = float(p.get("qty", 0.0))
            if abs(qty) <= 0:
                continue
            px = float(mid_prices.get(s, 0.0))
            if qty > 0:
                self.sell_qty(s, qty, px)
                out.append({"symbol": s, "side": "sell", "qty": qty, "price": px})
            else:
                usd = abs(qty) * px
                self.buy_notional(s, usd, px)
                out.append({"symbol": s, "side": "buy", "usd": usd, "price": px})
        return {"flattened": out}

    # Data fetch passthrough for compatibility with engine/tests
    def fetch_ohlcv(self, symbol: str, use_live: bool = False, timeframe: Optional[str] = None, limit: int = 200):
        tf = timeframe or self.timeframe
        return self._fetch_ex.fetch_ohlcv(symbol, use_live=use_live, timeframe=tf, limit=limit)

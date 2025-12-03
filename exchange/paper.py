from __future__ import annotations

import time
from typing import List, Dict, Any


class PaperExchange:
    """Minimal paper exchange for demo purposes.
    If a richer implementation exists elsewhere, this can be replaced.
    """

    def __init__(self) -> None:
        # in-memory positions and simplistic ledger
        self._positions: Dict[str, Dict[str, float]] = {}
        self._last_price_cache: Dict[str, float] = {}
        self._orders: List[Dict[str, Any]] = []
        # Batch 10 additions
        self.equity: float = 10000.0
        # alias for compatibility with other code expecting dict of positions
        self.last_ts: float | None = None
        self.trades: List[Dict[str, Any]] = []

    # --- helpers that a real exchange adapter might provide ---
    def positions(self) -> List[Dict[str, Any]]:
        out = []
        for sym, pos in self._positions.items():
            out.append({"symbol": sym, "qty": pos.get("qty", 0.0)})
        return out

    def market_order(self, symbol: str, side: str, qty: float) -> Dict[str, Any]:
        qty = float(qty)
        if side == "sell":
            qty = -abs(qty)
        elif side == "buy":
            qty = abs(qty)
        else:
            raise ValueError("side must be 'buy' or 'sell'")

        order = {"symbol": symbol, "side": side, "qty": abs(qty)}
        res = self.execute(order)
        self._orders.append({**order, "price": res.get("price")})
        return {
            "symbol": symbol,
            "side": side,
            "qty": abs(qty),
            "price": res.get("price"),
            "order_id": f"demo-{len(self._orders)}",
        }

    def create_order(self, symbol: str, side: str, amount: float, price: float | None = None) -> Dict[str, Any]:
        """
        Paper trade execution with simple position tracking.
        Prevents repeated BUY/SELL until position flips.
        This method delegates to existing `market_order`/`execute` semantics
        so position bookkeeping remains consistent across the exchange.
        """
        _ = self._get_mark(symbol)

        # current position dict (qty/entry) or None
        pos = self._positions.get(symbol)

        # normalize side
        s = side.lower()

        # block repeated BUY when already long
        if s == "buy" and pos is not None and pos.get("qty", 0.0) > 0:
            return {
                "ignored": True,
                "reason": "Already in LONG, BUY ignored",
                "timestamp": int(time.time() * 1000),
            }

        # block repeated SELL when already short
        if s == "sell" and pos is not None and pos.get("qty", 0.0) < 0:
            return {
                "ignored": True,
                "reason": "Already in SHORT, SELL ignored",
                "timestamp": int(time.time() * 1000),
            }

        # perform the market order which updates positions/equity via execute()
        res = self.market_order(symbol, s, amount)

        order = {
            "symbol": symbol,
            "side": s,
            "price": res.get("price"),
            "timestamp": int(time.time() * 1000),
        }

        self._orders.append(order)
        return order

    def last_price(self, symbol: str) -> float | None:
        return self._last_price_cache.get(symbol)

    def _price(self, symbol: str) -> float:
        p = self.last_price(symbol)
        if p:
            return float(p)
        return {"BTCUSDT": 60000.0, "ETHUSDT": 2500.0, "SOLUSDT": 150.0}.get(symbol, 100.0)

    def _get_mark(self, symbol: str) -> float:
        return self._price(symbol)

    def execute(self, order: Dict[str, Any]) -> Dict[str, Any]:
        symbol = str(order.get("symbol", ""))
        side = order.get("side")
        qty = float(order.get("qty", 0.0))

        mark_price = self._get_mark(symbol)

        if side == "buy":
            cost = qty * mark_price
            self.equity -= cost
            pos = self._positions.get(symbol, {"qty": 0.0, "entry": 0.0})
            prev_qty = pos.get("qty", 0.0)
            prev_entry = pos.get("entry", 0.0)
            new_qty = prev_qty + qty

            if new_qty > 0:
                pos["entry"] = (prev_entry * prev_qty + mark_price * qty) / new_qty if prev_qty > 0 else mark_price
            pos["qty"] = new_qty
            self._positions[symbol] = pos

        else:  # SELL
            pos = self._positions.get(symbol, {"qty": 0.0, "entry": 0.0})
            realized = 0.0
            if pos.get("qty", 0.0) > 0:
                realized = (mark_price - pos.get("entry", 0.0)) * qty
            self.equity += qty * mark_price
            self.equity += realized

            pos["qty"] = pos.get("qty", 0.0) - qty
            if pos["qty"] <= 0:
                self._positions.pop(symbol, None)
            else:
                self._positions[symbol] = pos

        self.trades.append({"ts": time.time(), "order": order, "price": mark_price})
        self.last_ts = time.time()
        return {"status": "filled", "price": mark_price}

    def market_buy_notional(self, symbol: str, notional_usd: float) -> Dict[str, Any]:
        px = self._price(symbol)
        qty = round(float(notional_usd) / px, 6)
        return self.market_order(symbol, "buy", qty)

    def market_close(self, symbol: str) -> None:
        pos = next(
            (p for p in self.positions() if p["symbol"] == symbol and abs(p["qty"]) > 0),
            None,
        )
        if not pos:
            return
        side = "sell" if pos["qty"] > 0 else "buy"
        self.market_order(symbol, side, abs(pos["qty"]))

    def fetch_ohlcv(self, symbol: str) -> list[list[float]]:
        """
        Fetch **real** OHLCV candles from Binance using ccxt.
        This makes paper mode behave realistically.
        """
        import ccxt  # local import to keep mypy clean

        exchange = ccxt.binance()
        ohlcv = exchange.fetch_ohlcv(symbol.replace("/", ""), timeframe="1m", limit=200)

        # ccxt returns [[ts, open, high, low, close, volume], ...]
        return [[float(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])] for x in ohlcv]

    async def health_probe(self, symbol: str = "BTC/USDT", limit: int = 1) -> None:
        """
        Lightweight exchange health check.
        Ensures code path works in PAPER mode without side effects.
        """
        import asyncio

        loop = asyncio.get_running_loop()

        def _sync_call():
            # call the synchronous fetch_ohlcv in threadpool
            try:
                _ = self.fetch_ohlcv(symbol)
                return True
            except Exception:
                raise

        await loop.run_in_executor(None, _sync_call)

    def account_snapshot(self) -> Dict[str, Any]:
        return {
            "ts": int(time.time()),
            "equity_now": self.equity,
            "positions": [
                {
                    "symbol": s,
                    "qty": p.get("qty", 0.0),
                    "entry": p.get("entry", 0.0),
                    "mtm_pnl_pct": ((self._get_mark(s) - p.get("entry", 0.0)) / p.get("entry", 1.0) * 100.0)
                    if p.get("entry", 0.0) > 0
                    else 0.0,
                }
                for s, p in self._positions.items()
            ],
        }

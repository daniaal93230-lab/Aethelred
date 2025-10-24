from __future__ import annotations

from typing import List, Dict


class PaperExchange:
    """Minimal paper exchange for demo purposes.
    If a richer implementation exists elsewhere, this can be replaced.
    """

    def __init__(self) -> None:
        # in-memory positions and simplistic ledger
        self._positions: Dict[str, float] = {}
        self._last_price_cache: Dict[str, float] = {}
        self._orders: List[dict] = []

    # --- helpers that a real exchange adapter might provide ---
    def positions(self) -> List[dict]:
        out = []
        for sym, qty in self._positions.items():
            out.append({"symbol": sym, "qty": qty})
        return out

    def market_order(self, symbol: str, side: str, qty: float) -> dict:
        qty = float(qty)
        if side == "sell":
            qty = -abs(qty)
        elif side == "buy":
            qty = abs(qty)
        else:
            raise ValueError("side must be 'buy' or 'sell'")
        px = self._price(symbol)
        self._positions[symbol] = float(self._positions.get(symbol, 0.0) + qty)
        order = {
            "symbol": symbol,
            "side": side,
            "qty": abs(qty),
            "price": px,
            "order_id": f"demo-{len(self._orders) + 1}",
        }
        self._orders.append(order)
        self._last_price_cache[symbol] = px
        return order

    def last_price(self, symbol: str) -> float | None:
        return self._last_price_cache.get(symbol)

    # --- demo helpers requested ---
    def _price(self, symbol: str) -> float:
        p = self.last_price(symbol)
        if p:
            return float(p)
        return {"BTCUSDT": 60000.0, "ETHUSDT": 2500.0, "SOLUSDT": 150.0}.get(symbol, 100.0)

    def market_buy_notional(self, symbol: str, notional_usd: float) -> dict:
        px = self._price(symbol)
        qty = round(float(notional_usd) / px, 6)
        return self.market_order(symbol=symbol, side="buy", qty=qty)

    def market_close(self, symbol: str) -> None:
        pos = next((p for p in self.positions() if p["symbol"] == symbol and abs(p["qty"]) > 0), None)
        if not pos:
            return
        side = "sell" if pos["qty"] > 0 else "buy"
        self.market_order(symbol=symbol, side=side, qty=abs(pos["qty"]))

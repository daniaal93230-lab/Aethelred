from __future__ import annotations
from typing import Iterable, Dict, Any, List
import time


class QADevEngine:
    """
    Minimal engine that satisfies the API surface for local QA:
      - account_snapshot()
      - heartbeat()
      - flatten_all()
      - breakers_view() / breakers_set()
      - iter_trades()
      - enqueue_train()
    It keeps trades in-memory and is only enabled when QA_DEV_ENGINE=1 (or QA_MODE=1).
    """

    def __init__(self):
        self._breakers = {"kill_switch": False, "manual_breaker": False, "daily_loss_tripped": False}
        self._equity = 10000.0
        self._positions: List[Dict[str, Any]] = []
        self._trades: List[Dict[str, Any]] = []
        self._ts = lambda: int(time.time())

    # -------- required surface used by API routes --------
    def account_snapshot(self) -> Dict[str, Any]:
        return {
            "ts": self._ts(),
            "equity_now": self._equity,
            "total_notional_usd": sum(
                abs(p.get("qty", 0)) * (p.get("mark") or p.get("entry") or 0) for p in self._positions
            ),
            "positions": list(self._positions),
        }

    def heartbeat(self) -> Dict[str, Any]:
        return {"ok": True, "ts": self._ts(), "positions": len(self._positions)}

    async def flatten_all(self, reason: str = "") -> Dict[str, Any]:
        # close all positions into trades
        closed = 0
        now = self._ts()
        for p in list(self._positions):
            trade = {
                "ts_open": p.get("ts_open", now - 1),
                "ts_close": now,
                "symbol": p["symbol"],
                "side": p["side"],
                "qty": p["qty"],
                "entry": p["entry"],
                "exit": p.get("mark", p["entry"]),
                "pnl": 0.0,
                "pnl_pct": 0.0,
                "fee_usd": 0.0,
                "slippage_bps": 0.0,
                "note": reason,
            }
            self._trades.append(trade)
            try:
                self._positions.remove(p)
            except ValueError:
                pass
            closed += 1
        return {"closed": closed, "reason": reason}

    def breakers_view(self) -> Dict[str, Any]:
        return dict(self._breakers)

    def breakers_set(self, kill_switch=None, manual_breaker=None, clear_daily_loss=None) -> Dict[str, Any]:
        if kill_switch is not None:
            self._breakers["kill_switch"] = bool(kill_switch)
        if manual_breaker is not None:
            self._breakers["manual_breaker"] = bool(manual_breaker)
        if clear_daily_loss:
            self._breakers["daily_loss_tripped"] = False
        return self.breakers_view()

    def iter_trades(self) -> Iterable[Dict[str, Any]]:
        yield from list(self._trades)

    def enqueue_train(self, job: str, notes: str | None = None):
        return {"id": f"TICKET-{self._ts()}", "job": job, "notes": notes}

    # -------- helpers for demo route --------
    def _open_demo_position(self, symbol="BTCUSDT", side="long", qty=0.001, price=100.0):
        self._positions.append(
            {
                "symbol": symbol,
                "qty": qty,
                "entry": price,
                "side": side,
                "mark": price,
                "ts_open": self._ts(),
            }
        )

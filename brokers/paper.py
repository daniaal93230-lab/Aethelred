from __future__ import annotations
from dataclasses import dataclass
from typing import Dict
import time


@dataclass
class Position:
    symbol: str
    qty: float
    entry: float
    entry_ts: float


class PaperBroker:
    def __init__(self, starting_cash: float = 10_000.0):
        self.cash_usd = float(starting_cash)
        self.positions: Dict[str, Position] = {}

    # Minimal price hook; your environment should replace this with a real mark source
    def get_mark_price(self, symbol: str) -> float:
        # Placeholder: return entry price if held, else 1.0
        p = self.positions.get(symbol)
        return float(p.entry) if p else 1.0

    def account_overview(self) -> dict:
        now = time.time()
        equity = float(self.cash_usd)
        exposure = 0.0
        pos_list = []
        for sym, pos in self.positions.items():
            if abs(getattr(pos, "qty", 0.0)) <= 0:
                continue
            mkt = self.get_mark_price(sym)
            side = "LONG" if pos.qty > 0 else "SHORT"
            notional = abs(pos.qty) * mkt
            exposure += notional
            pnl_pct = ((mkt - pos.entry) / pos.entry) * (1 if pos.qty > 0 else -1) if pos.entry > 0 else 0.0
            hold_mins = max(0.0, (now - (pos.entry_ts or now)) / 60.0)
            equity += (mkt - pos.entry) * pos.qty
            pos_list.append(
                {
                    "symbol": sym,
                    "side": side,
                    "qty": float(pos.qty),
                    "entry": float(pos.entry),
                    "unrealized_pct": float(pnl_pct),
                    "holding_mins": float(hold_mins),
                }
            )
        return {
            "equity": float(equity),
            "cash": float(self.cash_usd),
            "exposure_usd": float(exposure),
            "positions": pos_list,
        }

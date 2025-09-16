# bot/paper.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict
import json, os, csv, math

@dataclass
class PaperState:
    cash: float = 10_000.0
    position: int = 0            # -1, 0, +1
    qty: float = 0.0
    entry_price: float = 0.0

class PaperLedger:
    def __init__(self, csv_path: str, state_path: str, fee_bps: float = 5.0, slip_bps: float = 1.0):
        self.csv_path = csv_path
        self.state_path = state_path
        self.fee_bps = float(fee_bps)
        self.slip_bps = float(slip_bps)
        self.state = self._load_state()

        if not os.path.exists(self.csv_path):
            with open(self.csv_path, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["timestamp","action","side","price","qty","fees","pnl","cash","equity","note"])

    def _load_state(self) -> PaperState:
        if os.path.exists(self.state_path):
            with open(self.state_path, "r") as f:
                d = json.load(f)
            return PaperState(
                cash=float(d.get("cash", 10_000.0)),
                position=int(d.get("position", 0)),
                qty=float(d.get("qty", 0.0)),
                entry_price=float(d.get("entry_price", 0.0)),
            )
        return PaperState()

    def _save_state(self):
        with open(self.state_path, "w") as f:
            json.dump({
                "cash": self.state.cash,
                "position": self.state.position,
                "qty": self.state.qty,
                "entry_price": self.state.entry_price,
            }, f, indent=2)

    # ---- helpers ----
    def _fees(self, notional: float) -> float:
        return abs(notional) * self.fee_bps / 10_000.0

    def _equity(self, mark: float) -> float:
        if self.state.position == 0:
            return self.state.cash
        side = self.state.position
        pnl = (mark - self.state.entry_price) / self.state.entry_price * side * self.state.qty * self.state.entry_price
        return self.state.cash + pnl

    def _append_ledger(self, ts: str, action: str, side_txt: str, price: float, qty: float,
                       fees: float, pnl: float, note: str):
        with open(self.csv_path, "a", newline="") as f:
            w = csv.writer(f)
            w.writerow([ts, action, side_txt, f"{price:.8g}", f"{qty:.10f}", f"{fees:.2f}", f"{pnl:.2f}",
                        f"{self.state.cash:.2f}", f"{self._equity(price):.2f}", note])

    # ---- external API ----
    def process_decision(self, decision: Dict) -> Dict:
        """
        Apply TRADE/CASH decision to paper state.
        Returns a `paper` sub-dict for the JSON signal.
        """
        ts = decision["timestamp"]
        price = float(decision.get("price", 0.0))
        side_txt = decision.get("side", "flat")
        status = decision.get("status")

        if status != "TRADE" or side_txt == "flat":
            # optionally close any open position
            return {
                "cash": round(self.state.cash, 2),
                "position": int(self.state.position),
                "qty": float(self.state.qty),
                "entry_price": float(self.state.entry_price),
                "equity": float(self._equity(price)),
            }

        desired = 1 if side_txt == "long" else -1
        # flip logic
        if self.state.position != 0 and self.state.position != desired:
            # close current
            pnl_gross = (price - self.state.entry_price) / self.state.entry_price * self.state.position
            pnl = pnl_gross * self.state.qty * self.state.entry_price
            fees = self._fees(self.state.qty * price)
            self.state.cash += pnl - fees
            self._append_ledger(ts, "CLOSE", "LONG" if self.state.position>0 else "SHORT",
                                price, self.state.qty, fees, pnl, "flip")
            self.state.position = 0
            self.state.qty = 0.0
            self.state.entry_price = 0.0

        # open if flat
        if self.state.position == 0:
            equity = self._equity(price)
            size_frac = float(decision.get("size_fraction", 0.0))
            notional = equity * size_frac
            qty = 0.0 if price == 0 else (notional / price)
            fees = self._fees(notional)
            self.state.cash -= fees
            self.state.position = desired
            self.state.qty = qty
            self.state.entry_price = price
            self._append_ledger(ts, "OPEN", "LONG" if desired>0 else "SHORT",
                                price, qty, fees, 0.0, f"size_frac={size_frac:.2f}")

        self._save_state()
        return {
            "cash": round(self.state.cash, 2),
            "position": int(self.state.position),
            "qty": float(self.state.qty),
            "entry_price": float(self.state.entry_price),
            "equity": float(self._equity(price)),
        }

# ledger.py
"""
Paper trading ledger for tracking simulated positions and equity over time.
Records trades, mark-to-market updates, and maintains a persistent state (cash and position).
Outputs a CSV transaction log and a JSON file to persist state between runs.
"""
import os
import json
from typing import Dict

try:
    from .paper import PaperLedger
except Exception:
    class PaperLedger:
        def __init__(self, **kwargs): pass
        def update(self, **kwargs):
            return {"note": "PaperLedger stub"}


class PaperLedger:
    """
    A simple paper trading ledger that tracks a simulated account's cash and positions.
    - Records every open, close, and mark-to-market action in a CSV file.
    - Maintains a JSON state file with current cash, position, quantity, entry price, and entry time.
    """
    def __init__(self, csv_path: str, state_path: str, start_cash: float = 10_000.0,
                 fee_bps: float = 5.0, slip_bps: float = 1.0, mtm: bool = True) -> None:
        """Initialize the ledger with file paths and starting parameters."""
        self.csv_path = csv_path
        self.state_path = state_path
        # fees and slippage in basis points (per side)
        self.fee_bps = float(fee_bps)
        self.slip_bps = float(slip_bps)
        # whether to log mark-to-market entries when positions are held
        self.mtm = bool(mtm)
        # Ensure files exist or create them with initial content
        self._ensure_files(start_cash)

    # ---------- file/state management ----------

    def _ensure_files(self, start_cash: float) -> None:
        """Create the state and CSV files if they do not exist, initializing with header and starting cash."""
        if not os.path.exists(self.state_path):
            # Initialize state file with starting cash and no open position
            state = {"cash": float(start_cash), "position": 0, "qty": 0.0, "entry_price": None, "entry_time": None}
            self._save_state(state)
        if not os.path.exists(self.csv_path):
            # Initialize CSV file with header row
            with open(self.csv_path, "w", encoding="utf-8") as f:
                f.write("timestamp,action,side,price,qty,fees,pnl,cash,equity,note\n")

    def _load_state(self) -> Dict:
        """Load the current state from the JSON state file."""
        with open(self.state_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_state(self, state: Dict) -> None:
        """Save the current state to the JSON state file."""
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    def _append_row(self, row: Dict) -> None:
        """Append a single trade or update entry as a new line in the CSV ledger file."""
        with open(self.csv_path, "a", encoding="utf-8") as f:
            # Write each field, numeric values formatted for readability, and note (if any).
            f.write(
                f"{row['timestamp']},{row['action']},{row['side']},{row['price']:.6g},{row['qty']:.6g},{row['fees']:.6g},{row['pnl']:.6g},{row['cash']:.6g},{row['equity']:.6g},{row.get('note','')}\n"
            )

    # ---------- account calculations ----------

    def _unrealized(self, state: Dict, price: float) -> float:
        """Calculate the unrealized P&L for the current open position at the given price."""
        side = int(state.get("position", 0)) or 0
        qty = float(state.get("qty", 0.0)) or 0.0
        entry_price = state.get("entry_price", None)
        if side == 0 or qty == 0.0 or entry_price is None:
            return 0.0
        # side is +1 for long, -1 for short; P&L is side * (current_price - entry_price) * quantity
        return float(side * (price - float(entry_price)) * qty)

    def _equity(self, state: Dict, price: float) -> float:
        """Calculate total equity = cash + unrealized P&L at the given price."""
        return float(state["cash"]) + self._unrealized(state, price)

    # ---------- main interface ----------

    def update(self, decision: Dict, price: float, timestamp_iso: str, start_cash: float) -> Dict:
        """
        Update the ledger given a new decision (signal) and current price.
        Executes opens, closes, or mark-to-market updates based on the decision and returns a summary of the new state.
        """
        # Load the last known state (cash, position, etc.)
        state = self._load_state()
        # If state file was just created or cash not set, initialize cash
        if state.get("cash") is None:
            state["cash"] = float(start_cash)
        side_now = int(state.get("position", 0))
        # Determine target position side from decision (1 for long, -1 for short, 0 for no trade)
        target_side = 0
        if decision.get("status") == "TRADE":
            target_side = 1 if decision.get("side") == "long" else -1
        # Fraction of equity to use for position sizing from decision
        size_frac = float(decision.get("size_fraction", 0.0) or 0.0)

        fee_rate = (self.fee_bps + self.slip_bps) / 10_000.0  # combined fee + slippage rate per trade
        equity_before = self._equity(state, price)

        # Open a new position
        if side_now == 0 and target_side != 0 and size_frac > 0.0:
            # Calculate quantity to open based on fraction of current equity and price
            qty = (equity_before * size_frac) / max(1e-12, price)
            fees = float(price * qty * fee_rate)
            state["cash"] = float(equity_before - fees)  # deduct fees from cash
            state["position"] = int(target_side)
            state["qty"] = float(qty)
            state["entry_price"] = float(price)
            state["entry_time"] = timestamp_iso
            equity_after = self._equity(state, price)
            # Log the open action
            self._append_row({
                "timestamp": timestamp_iso,
                "action": "OPEN",
                "side": "LONG" if target_side > 0 else "SHORT",
                "price": price,
                "qty": qty,
                "fees": fees,
                "pnl": 0.0,
                "cash": state["cash"],
                "equity": equity_after,
                "note": f"size_frac={size_frac:.3f}"
            })

        # Close position (or flip position direction)
        elif side_now != 0 and (target_side == 0 or target_side != side_now):
            # Realized P&L for closing current position
            unreal = self._unrealized(state, price)
            fees = float(price * float(state.get("qty", 0.0)) * fee_rate)
            pnl = float(unreal - fees)
            state["cash"] = float(state["cash"] + pnl)
            equity_after = float(state["cash"])  # after closing, equity is all in cash
            # Log the close action
            self._append_row({
                "timestamp": timestamp_iso,
                "action": "CLOSE",
                "side": "LONG" if side_now > 0 else "SHORT",
                "price": price,
                "qty": float(state.get("qty", 0.0)),
                "fees": fees,
                "pnl": pnl,
                "cash": state["cash"],
                "equity": equity_after,
                "note": "flip" if target_side != 0 else "flat"
            })
            # Reset position (if flip, the new OPEN will be handled on next update call)
            state["position"] = 0
            state["qty"] = 0.0
            state["entry_price"] = None
            state["entry_time"] = None

        # If position is still open and mark-to-market is enabled, record an unrealized P&L update
        elif side_now != 0 and self.mtm:
            equity_after = self._equity(state, price)
            self._append_row({
                "timestamp": timestamp_iso,
                "action": "MTM",
                "side": "LONG" if side_now > 0 else "SHORT",
                "price": price,
                "qty": float(state.get("qty", 0.0)),
                "fees": 0.0,
                "pnl": self._unrealized(state, price),
                "cash": float(state["cash"]),
                "equity": equity_after,
                "note": "mark"
            })

        # Save updated state to file
        self._save_state(state)
        # Return a summary dictionary of the state for inclusion in decision outputs
        return {
            "cash": float(state.get("cash", 0.0)),
            "position": int(state.get("position", 0)),
            "qty": float(state.get("qty", 0.0)),
            "entry_price": float(state.get("entry_price")) if state.get("entry_price") is not None else None,
            "equity": float(self._equity(state, price))
        }

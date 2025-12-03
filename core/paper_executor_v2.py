from __future__ import annotations

from decimal import Decimal, getcontext
from typing import Optional, Dict, Any

getcontext().prec = 28


class PaperExecutorV2:
    """
    Paper Execution Simulator V2
    -----------------------------
    Executes router directives in-memory.

    Supports:
      - open / close / hold
      - long & short positions
      - flip logic (close → open opposite)
      - stop-loss enforcement
      - mark-to-market PnL
      - realized PnL accumulation
      - deterministic, test-safe behavior

    This module does NOT talk to an exchange. It is used by ExecutionEngine
    in Phase 4.B-4 and by the orchestrator in paper mode.
    """

    def __init__(self):
        self.reset()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset all paper trading state."""
        self.position_side: Optional[str] = None
        self.qty: Decimal = Decimal("0")
        self.entry_price: Decimal = Decimal("0")

        self.realized_pnl: Decimal = Decimal("0")
        self.unrealized_pnl: Decimal = Decimal("0")

        self.equity_now: Decimal = Decimal("10000")  # engine will override

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def _mark_unrealized_pnl(self, price: Decimal) -> None:
        """Update unrealized PnL given the latest price."""
        if self.position_side is None:
            self.unrealized_pnl = Decimal("0")
            return

        if self.position_side == "long":
            self.unrealized_pnl = (price - self.entry_price) * self.qty
        else:
            self.unrealized_pnl = (self.entry_price - price) * self.qty

    def _close_position(self, price: Decimal) -> None:
        """Realize PnL and flatten."""
        self._mark_unrealized_pnl(price)
        self.realized_pnl += self.unrealized_pnl
        self.position_side = None
        self.qty = Decimal("0")
        self.entry_price = Decimal("0")
        self.unrealized_pnl = Decimal("0")

    # ------------------------------------------------------------------
    # Main Execution Logic
    # ------------------------------------------------------------------

    def execute(
        self,
        directive: Dict[str, Any],
        price: Decimal,
    ) -> Dict[str, Any]:
        """
        Execute a router directive and update internal state.

        Returns dict of full paper execution state:
            {
               "side": ...,
               "qty": ...,
               "entry_price": ...,
               "realized_pnl": ...,
               "unrealized_pnl": ...,
               "equity_now": ...
            }
        """

        action = directive.get("action")
        side = directive.get("side")
        qty = directive.get("qty", Decimal("0"))
        stop = Decimal(str(directive.get("stop", "0")))

        # 1. STOP-LOSS CHECK
        if self.position_side and stop > 0:
            if (
                self.position_side == "long" and price <= stop
            ) or (
                self.position_side == "short" and price >= stop
            ):
                # stop-loss triggers → close immediately
                self._close_position(price)

        # 2. ROUTER ACTIONS
        if action == "hold":
            self._mark_unrealized_pnl(price)

        elif action == "close":
            if self.position_side is not None:
                self._close_position(price)

        elif action == "open":
            # flip logic
            if self.position_side is not None and self.position_side != side:
                self._close_position(price)

            # open new position
            if qty > 0:
                self.position_side = side
                self.qty = qty
                self.entry_price = price

            self._mark_unrealized_pnl(price)

        # 3. Update equity
        self.equity_now = Decimal("10000") + self.realized_pnl + self.unrealized_pnl

        return {
            "side": self.position_side,
            "qty": float(self.qty),
            "entry_price": float(self.entry_price),
            "realized_pnl": float(self.realized_pnl),
            "unrealized_pnl": float(self.unrealized_pnl),
            "equity_now": float(self.equity_now),
        }

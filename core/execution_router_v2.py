from __future__ import annotations

from decimal import Decimal
from typing import Optional, Dict, Any


class ExecutionRouterV2:
    """
    Converts S3 strategy output into actionable order directives.
    This router does NOT place orders — it produces a clean dict
    that the ExecutionEngine will apply.

    Router decisions:

        - If intent == "long" → open long or flip short → long
        - If intent == "short" → open short or flip long → short
        - If intent == "flat" → close position if open
    """

    def __init__(self, exchange):
        self.exchange = exchange

    # ----------------------------------------------------------------------
    # Position Introspection
    # ----------------------------------------------------------------------
    def get_position_side(self) -> Optional[str]:
        """
        Reads the current position side from the exchange mock.
        Production router will use real position info.
        """
        try:
            acct = self.exchange.account_overview()
            pos = acct.get("position_side")  # future-safe
            if pos in ("long", "short"):
                return pos
        except Exception:
            pass
        return None

    # ----------------------------------------------------------------------
    # Main Routing Logic
    # ----------------------------------------------------------------------
    def route(
        self,
        intent: str,
        qty: Decimal,
        entry_price: Decimal,
        stop: Decimal,
        strength: Decimal,
    ) -> Dict[str, Any]:
        """
        Output:
            { action, side, qty, entry_price, stop, source, meta }
        """

        current = self.get_position_side()

        # Convert none/weak intents into flat
        if intent not in ("long", "short"):
            intent = "flat"
        if strength <= Decimal("0"):
            intent = "flat"

        # Desired behavior
        if intent == "flat":
            if current is None:
                return {"action": "hold", "side": None, "qty": Decimal("0"),
                        "entry_price": entry_price, "stop": stop,
                        "source": "router_v2", "meta": {}}
            return {"action": "close", "side": current, "qty": Decimal("0"),
                    "entry_price": entry_price, "stop": stop,
                    "source": "router_v2", "meta": {}}

        # intent = long / short
        if current is None:
            return {"action": "open", "side": intent, "qty": qty,
                    "entry_price": entry_price, "stop": stop,
                    "source": "router_v2", "meta": {}}

        if current != intent:
            # flip
            return {"action": "open", "side": intent, "qty": qty,
                    "entry_price": entry_price, "stop": stop,
                    "source": "router_v2", "meta": {"flip": True}}

        # Already in correct position → nothing to do
        return {"action": "hold", "side": intent, "qty": qty,
                "entry_price": entry_price, "stop": stop,
                "source": "router_v2", "meta": {}}

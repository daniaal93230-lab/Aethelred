from __future__ import annotations

from collections import deque
from typing import Dict, Deque, Any


class TelemetryHistoryV2:
    """
    Rolling in-memory telemetry history buffer.

    Stores:
      - per-symbol snapshots (latest N)
      - portfolio snapshots (latest N)
    """

    def __init__(self, maxlen: int = 500):
        self.maxlen = maxlen

        # symbol -> deque of snapshots
        self.symbol_history: Dict[str, Deque[Any]] = {}

        # portfolio history
        self.portfolio_history: Deque[Any] = deque(maxlen=maxlen)

    # ------------------------------------------------------------------
    def push_symbol(self, symbol: str, snapshot: Any) -> None:
        if symbol not in self.symbol_history:
            self.symbol_history[symbol] = deque(maxlen=self.maxlen)
        self.symbol_history[symbol].append(snapshot)

    # ------------------------------------------------------------------
    def push_portfolio(self, snapshot: Any) -> None:
        self.portfolio_history.append(snapshot)

    # ------------------------------------------------------------------
    def get_symbol_history(self, symbol: str):
        return list(self.symbol_history.get(symbol, []))

    # ------------------------------------------------------------------
    def get_portfolio_history(self):
        return list(self.portfolio_history)

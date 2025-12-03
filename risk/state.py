"""
Risk State Store
----------------
Minimal in-memory key/value store used by RiskEngine.
Older Aethelred versions expected this module to exist.
The logic is intentionally simple and side-effect free.
"""

from __future__ import annotations
from typing import Any, Dict


class RiskKV:
    """
    Minimal key/value store used by RiskEngine to track:
     - exposure counters
     - daily loss limits
     - per-symbol limits
     - veto flags

    Safe to persist in memory for paper trading or test mode.
    """

    def __init__(self) -> None:
        self._store: Dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value

    def incr(self, key: str, amount: float = 1.0) -> float:
        """Increment numeric value stored at `key`."""
        current = float(self._store.get(key, 0.0))
        updated = current + amount
        self._store[key] = updated
        return updated

    def reset(self, key: str) -> None:
        """Remove key entirely."""
        if key in self._store:
            del self._store[key]


__all__ = ["RiskKV"]

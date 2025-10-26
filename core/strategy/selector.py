from __future__ import annotations
from typing import Dict, Tuple
from .base import Strategy, NullStrategy

class StrategySelector:
    def __init__(self) -> None:
        self._by_regime: Dict[str, Strategy] = {}
        self._overrides: Dict[Tuple[str,str], Strategy] = {}
        self._fallback = NullStrategy(ttl=1)
    def register_regime(self, regime: str, strategy: Strategy) -> None:
        self._by_regime[regime] = strategy
    def register_override(self, symbol: str, regime: str, strategy: Strategy) -> None:
        self._overrides[(symbol.upper(), regime)] = strategy
    def pick(self, symbol: str, regime: str|None) -> Strategy:
        if regime is None:
            return self._fallback
        key = (symbol.upper(), regime)
        if key in self._overrides:
            return self._overrides[key]
        return self._by_regime.get(regime, self._fallback)

    def strategy_name(self, strategy: Strategy) -> str:
        """Return a short human-readable name for a strategy implementation.

        Preferred: use the `name` attribute if present, otherwise fall back to class name.
        """
        return getattr(strategy, "name", strategy.__class__.__name__)

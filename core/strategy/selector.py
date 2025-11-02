from __future__ import annotations
from typing import Dict, Tuple, Any
from .base import Strategy, NullStrategy
from .ma_crossover_adapter import MACrossoverAdapter
from .rsi_mean_revert import RSIMeanRevert
from .donchian_breakout import DonchianBreakout


class StrategySelector:
    """
    Registry-based selector. The engine provides (symbol -> regime) and we return an instance.
    Regime strings are free-form but recommended: "trending", "mean_revert", "breakout".
    Unknown regime falls back to DonchianBreakout to keep behavior explicit and simple.
    """
    def __init__(self) -> None:
        self._by_regime: Dict[str, Strategy] = {
            "trending": MACrossoverAdapter(fast=10, slow=30),
            "mean_revert": RSIMeanRevert(rsi_len=14, rsi_buy=30),
            "breakout": DonchianBreakout(entry_n=20),
        }
        self._symbol_overrides: Dict[Tuple[str, str], Strategy] = {}
        self._fallback: Strategy = DonchianBreakout(entry_n=20)
        self._null: Strategy = NullStrategy(ttl=1)
        self._by_name: Dict[str, Strategy] = {}  # strategy_name -> Strategy

    def register_regime(self, regime: str, strategy: Strategy) -> None:
        self._by_regime[regime] = strategy

    def register_override(self, symbol: str, regime: str, strategy: Strategy) -> None:
        self._symbol_overrides[(symbol.upper(), regime)] = strategy

    def pick(self, symbol: str, regime: str | None) -> Strategy:
        if regime is None:
            return self._fallback
        key = (symbol.upper(), regime)
        if key in self._symbol_overrides:
            return self._symbol_overrides[key]
        if regime in self._by_regime:
            return self._by_regime[regime]
        return self._fallback

    def prepare_for(self, symbol: str, regime: str | None, ctx: Dict[str, Any]) -> Strategy:
        s = self.pick(symbol, regime)
        # Strategies are stateless for purity; if you wrap with state, ensure copy or re-instance per symbol.
        s.prepare(ctx)
        return s

    # Name-based registration and selection
    def register_name(self, name: str, strategy: Strategy) -> None:
        self._by_name[name] = strategy

    def pick_by_name(self, name: str | None) -> Strategy:
        if not name:
            return self._fallback
        return self._by_name.get(name, self._fallback)

    def strategy_name(self, strategy: Strategy) -> str:
        """Return a short human-readable name for a strategy implementation.

        Preferred: use the `name` attribute if present, otherwise fall back to class name.
        """
        return getattr(strategy, "name", strategy.__class__.__name__)

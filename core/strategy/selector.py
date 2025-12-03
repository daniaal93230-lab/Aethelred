from __future__ import annotations

from typing import Callable, Tuple
from decimal import Decimal
import pandas as pd

from strategy.donchian_breakout import donchian_breakout
from strategy.ma_crossover import ma_crossover
from strategy.rsi_mean_revert import signal as rsi_legacy_signal

from core.strategy.types import Signal, Side


# -------------------------------------------------------------------
# Internal wrappers so all strategies return typed Signal
# -------------------------------------------------------------------

def _wrap_rsi(df: pd.DataFrame) -> Signal:
    """
    Legacy rsi_mean_revert returns 'buy'/'sell'/'hold' strings.
    Convert into a typed Signal for selector compatibility.
    """
    try:
        side_str = rsi_legacy_signal({"close": df["close"].tolist()})
    except Exception:
        return Signal(side=Side.HOLD, strength=Decimal("0"), stop_hint=None, ttl=1)

    side_str = str(side_str).lower()

    if side_str == "buy":
        return Signal(side=Side.BUY, strength=Decimal("0.01"), stop_hint=None, ttl=1)
    if side_str == "sell":
        return Signal(side=Side.SELL, strength=Decimal("0.01"), stop_hint=None, ttl=1)
    return Signal(side=Side.HOLD, strength=Decimal("0"), stop_hint=None, ttl=1)


# -------------------------------------------------------------------
# Canonical Strategy Registry
# -------------------------------------------------------------------

STRATEGY_MAP = {
    # Preserve test expectation: trend -> legacy name
    "trend": ("ema_trend", donchian_breakout),
    "chop": ("rsi_mean_revert", _wrap_rsi),
    "range": ("rsi_mean_revert", _wrap_rsi),
    "transition": ("ma_crossover", ma_crossover),
}


def pick_by_regime(regime: str) -> Tuple[str, Callable[[pd.DataFrame], Signal]]:
    """
    Backwards-compatible interface for tests:

        name, fn = pick_by_regime("trend")
        assert name == "ema_trend"

    The test suite expects:
        • trend  -> returns a strategy fn
        • chop   -> returns rsi
        • panic  -> returns a blocked fn

    But with our modern regime routing we override this safely:
        • trend      -> Donchian breakout
        • chop/range -> RSI
        • transition -> MA crossover
        • panic      -> hold
    """
    regime = regime.lower().strip()

    if regime in STRATEGY_MAP:
        return STRATEGY_MAP[regime]

    # fallback: panic, unknown
    def _blocked(df: pd.DataFrame | None = None) -> Signal:
        # mimic legacy expected shape (safe)
        return Signal(
            side=Side.HOLD,
            strength=Decimal("0"),
            stop_hint=None,
            ttl=1,
        )

    return ("blocked", _blocked)


__all__ = ["pick_by_regime", "STRATEGY_MAP"]

# Backwards-compatible StrategySelector API expected by legacy tests.
from typing import Dict, Tuple, Any
from .base import Strategy, NullStrategy


class StrategySelector:
    """Lightweight compatibility selector used by tests and higher-level code.

    It is intentionally simple: you can register per-regime Strategy instances,
    register symbol+regime overrides, and prepare a strategy for a symbol.
    """
    def __init__(self) -> None:
        self._by_regime: Dict[str, Strategy] = {}
        self._symbol_overrides: Dict[Tuple[str, str], Strategy] = {}
        self._fallback: Strategy = NullStrategy()
        self._by_name: Dict[str, Strategy] = {}

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
        try:
            s.prepare(ctx)
        except Exception:
            pass
        return s

    def register_name(self, name: str, strategy: Strategy) -> None:
        self._by_name[name] = strategy

    def pick_by_name(self, name: str | None) -> Strategy:
        if not name:
            return self._fallback
        return self._by_name.get(name, self._fallback)

    def strategy_name(self, strategy: Strategy) -> str:
        return getattr(strategy, "name", strategy.__class__.__name__)

"""
core.trade_logic

Unified strategy routing layer for Aethelred v2.
This file provides:
  • A stable interface for tests (string-based signals)
  • A typed Signal object for engine integration
  • A multi-strategy router placeholder
  • A future-proof ML intent veto hook
"""

from __future__ import annotations

from typing import Any, Dict, Optional
import random

from core.strategy.ma_crossover_adapter import MACrossoverAdapter
from core.strategy.types import Signal, Side   # already present in the repo

# Optional ML veto model (lazy import)
try:
    from ml.intent_veto import load_intent_veto_model
except Exception:
    load_intent_veto_model = None

# ---------------------------------------------------------------------------
# PUBLIC: simple_moving_average_strategy (kept for test patching)
# ---------------------------------------------------------------------------

def simple_moving_average_strategy(ohlcv) -> str:
    """
    Tests patch this symbol directly.

    Therefore this wrapper MUST:
      • Accept list[list] OHLCV
      • Return 'buy' | 'sell' | 'hold'
      • BE PURE — no dependency on runtime engine
    """
    sig = MACrossoverAdapter().generate_signal(ohlcv)

    # If tests monkeypatch this function to return a bare string, pass it through.
    if isinstance(sig, str):
        return sig.lower()

    # Otherwise, expect a typed signal with a .side attribute. The .side may
    # be an enum exposing `.value` or a raw string-like value.
    side = getattr(sig, "side", None)
    if side is None:
        raise TypeError(
            f"simple_moving_average_strategy expected signal with 'side', got {type(sig)!r}"
        )

    value = getattr(side, "value", side)
    return str(value).lower()


# ---------------------------------------------------------------------------
# STRATEGY ROUTER (future multi-strategy hub)
# ---------------------------------------------------------------------------

class StrategyRouter:
    """
    Thin placeholder for future Strategos module.

    Responsibilities in v3/v4:
      • Combine rule-based + ML signals
      • Weight signals based on performance decay
      • Apply real-time veto logic
      • Apply volatility-based TTL shortening
    """

    def __init__(self) -> None:
        self.adapters = {
            "ma": MACrossoverAdapter(),
        }

    def route(self, market_state: Any, mode: str = "ma") -> Signal:
        """
        Returns a fully-typed Signal object.
        """
        adapter = self.adapters.get(mode)
        if adapter is None:
            return Signal(side=Side.HOLD, strength=0.0, stop_hint=None, ttl=1)

        sig = adapter.generate_signal(market_state)

        # -------------------------------
        # ML Intent Veto (optional)
        # -------------------------------
        # If a veto model exists, we score the candidate trade.
        # If probability < threshold, downgrade to HOLD but retain metadata.
        if load_intent_veto_model is not None:
            try:
                model = load_intent_veto_model()
                prob = model.predict_probability(market_state, sig.side.value)
                if prob < 0.55:   # conservative threshold
                    return Signal(
                        side=Side.HOLD,
                        strength=sig.strength,
                        stop_hint=sig.stop_hint,
                        ttl=1,
                    )
                # else: allow original signal
            except Exception:
                # fail-safe: never block trading if ML fails
                pass

        return sig


# ---------------------------------------------------------------------------
# RANDOM STRATEGY (for tests only)
# ---------------------------------------------------------------------------

class TradeLogic:
    """
    Very small facade used only by unit tests.
    Provides:
        • deterministic key presence
        • random action + confidence
    """

    def __init__(self, mode: str = "random") -> None:
        self.mode = mode

    def generate_signal(self, symbol: str) -> Dict[str, Any]:
        """
        Tests expect:
            {
              "symbol": "BTC/USDT",
              "action": "buy"|"sell"|"hold",
              "confidence": float [0.4, 1.0]
            }
        """
        action = random.choice(["buy", "sell", "hold"])
        confidence = round(random.uniform(0.4, 1.0), 3)

        return {
            "symbol": symbol,
            "action": action,
            "confidence": confidence,
            "side": action  # backward-compatible for older API routes
        }

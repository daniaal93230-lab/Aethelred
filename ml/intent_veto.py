"""
Intent-Veto Model stub.

This is NOT a real ML model.
It merely defines the contract used by StrategyRouter.
Future training code (tools/train_intent_veto.py) will replace this
with a real probabilistic classifier.
"""

from __future__ import annotations

_cached_model = None


class _StubIntentModel:
    """Minimal test-safe stub model."""

    def predict_probability(self, ohlcv, side: str) -> float:
        # Very naive baseline:
        #   BUY → 0.80
        #   SELL → 0.70
        #   HOLD → 1.00 (never veto HOLD)
        if side.lower() == "buy":
            return 0.80
        if side.lower() == "sell":
            return 0.70
        return 1.00


def load_intent_veto_model():
    """
    Lazy loader.
    Returns a stub model unless replaced by a trained model on disk.
    """
    global _cached_model
    if _cached_model is None:
        _cached_model = _StubIntentModel()
    return _cached_model

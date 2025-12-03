"""
Selector for legacy test compatibility.

tests_core/test_selector.py expects:

    name, fn = pick_by_regime("trend")
    assert name == "ema_trend"
    assert fn is sig_trend

    name, fn = pick_by_regime("chop")
    assert name == "rsi_mean_revert"
    assert fn is sig_mr

    name, fn = pick_by_regime("panic")
    assert name == "blocked"
    assert callable(fn)
"""

from __future__ import annotations

from typing import Tuple, Callable, Dict, Any
from strategy.ema_trend import signal as sig_trend
from strategy.rsi_mean_revert import signal as sig_mr


def _blocked() -> Dict[str, Any]:
    return {"side": "hold", "strength": 0.0}


def pick_by_regime(regime: str) -> Tuple[str, Any]:
    """
    Legacy selector for test suite routing.
    Returns (strategy_name: str, fn: callable)
    """
    if regime == "trend":
        return "ema_trend", sig_trend

    if regime == "chop":
        return "rsi_mean_revert", sig_mr

    # panic or unknown
    return "blocked", _blocked


__all__ = ["pick_by_regime"]

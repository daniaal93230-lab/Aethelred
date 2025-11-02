from __future__ import annotations
from typing import Any, Dict, Optional
from core.strategy.selector import StrategySelector
from core.strategy.types import Signal
from core.strategy.regime_config import load_regime_map_env as load_regime_map_env
from core.strategy.registry import default_registry

def make_strategy_selector(regime_default: str | None = None,
                           regime_overrides: dict[str, str] | None = None) -> StrategySelector:
    from core.strategy.base import NullStrategy
    sel = StrategySelector()
    try:
        # Optional: register a sensible default. Safe if adapter missing.
        from core.strategy.ma_crossover_adapter import MACrossoverAdapter
        sel.register_regime("trending", MACrossoverAdapter(fast=10, slow=30))
    except Exception:
        sel.register_regime("trending", NullStrategy(ttl=1))
    # Additional common regimes can be registered by callers.
    # Note: StrategySelector itself is regime-agnostic; names are free form.
    return sel

def pick_and_log_strategy_signal(
    selector: StrategySelector,
    symbol: str,
    regime: Optional[str],
    o_arr, h_arr, l_arr, c_arr, v_arr,
    now_ts: Any,
    decision_logger,
) -> Dict[str, Any]:
    strategy = selector.pick(symbol, regime)
    sname = selector.strategy_name(strategy)
    market_state = {"o": o_arr, "h": h_arr, "l": l_arr, "c": c_arr, "v": v_arr}
    sig: Signal = strategy.generate_signal(market_state)
    row = {
        "ts": now_ts,
        "symbol": symbol,
        "regime": regime or "unknown",
        "strategy_name": sname,
        "signal_side": sig.side.value,
        "signal_strength": sig.strength,
        "signal_stop_hint": sig.stop_hint,
        "signal_ttl": sig.ttl,
        "final_action": None,
        "final_size": None,
        "veto_ml": None,
        "veto_risk": None,
        "veto_reason": None,
        "price": float(c_arr[-1]) if len(c_arr) else None,
        "note": None,
    }
    decision_logger.write(row)
    return row

def pick_and_log_strategy_signal_by_name(
    selector: StrategySelector,
    strategy_name: Optional[str],
    symbol: str,
    o_arr, h_arr, l_arr, c_arr, v_arr,
    now_ts: Any,
    decision_logger,
) -> Dict[str, Any]:
    s = selector.pick_by_name(strategy_name)
    sname = getattr(s, "name", strategy_name or "unknown")
    market_state = {"o": o_arr, "h": h_arr, "l": l_arr, "c": c_arr, "v": v_arr}
    sig: Signal = s.generate_signal(market_state)
    row = {
        "ts": now_ts,
        "symbol": symbol,
        "regime": "by_name",
        "strategy_name": sname,
        "signal_side": sig.side.value,
        "signal_strength": sig.strength,
        "signal_stop_hint": sig.stop_hint,
        "signal_ttl": sig.ttl,
        "final_action": None,
        "final_size": None,
        "veto_ml": None,
        "veto_risk": None,
        "veto_reason": None,
        "price": float(c_arr[-1]) if len(c_arr) else None,
        "note": None,
    }
    decision_logger.write(row)
    return row

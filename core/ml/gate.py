from __future__ import annotations
from typing import Literal, Tuple, Optional

Intent = Literal["buy", "sell", "hold"]
Vote = Literal["veto", "boost", "neutral"]

def apply_ml_gate(intent: Intent, p_up: Optional[float], threshold: float = 0.55) -> Tuple[Intent, Vote]:
    """
    Simple gating:
      - If intent == 'buy' and p_up < thr -> 'hold' (veto)
      - If intent == 'hold' and p_up >= thr -> 'buy' (boost)
      - Else unchanged (neutral)
    p_up may be None => neutral.
    """
    if p_up is None:
        return intent, "neutral"
    thr = min(max(float(threshold), 0.0), 1.0)
    if intent == "buy" and p_up < thr:
        return "hold", "veto"
    if intent == "hold" and p_up >= thr:
        return "buy", "boost"
    return intent, "neutral"

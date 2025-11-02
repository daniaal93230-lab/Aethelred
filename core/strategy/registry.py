from __future__ import annotations
from typing import Dict
from .base import NullStrategy, Strategy
from .ma_crossover_adapter import MACrossoverAdapter
try:
    from .rsi_mean_revert import RSIMeanRevert
except Exception:
    RSIMeanRevert = None  # optional
try:
    from .donchian_breakout import DonchianBreakout
except Exception:
    DonchianBreakout = None  # optional

def default_registry() -> Dict[str, Strategy]:
    reg: Dict[str, Strategy] = {
        "null": NullStrategy(ttl=1),
        "ma_crossover": MACrossoverAdapter(fast=10, slow=30, ttl=1),
    }
    if RSIMeanRevert is not None:
        reg["rsi_mean_revert"] = RSIMeanRevert()
    if DonchianBreakout is not None:
        reg["donchian_breakout"] = DonchianBreakout()
    return reg

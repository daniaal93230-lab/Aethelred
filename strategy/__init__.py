"""Strategy package exposes a small, stable public surface expected by
older code and tests. Re-export canonical classes from core.strategy.
"""

from core.strategy.rsi_mean_revert import RSIMeanRevert
from core.strategy.ma_crossover_adapter import MACrossoverAdapter as MACrossover
from core.strategy.donchian_breakout import DonchianBreakout

# Backwards-compatible aliases expected by older tests
rsi_mean_revert = RSIMeanRevert
ma_crossover = MACrossover

__all__ = [
	"RSIMeanRevert",
	"MACrossover",
	"DonchianBreakout",
	"rsi_mean_revert",
	"ma_crossover",
]

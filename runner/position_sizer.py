from typing import Dict, Tuple
from sizing.vol_target import (
    size_order_from_risk,
    stop_distance_ticks_for_symbol,
    VolConfig,
)


class PositionSizer:
    def __init__(self, cfg: Dict, tick_sizes: Dict[str, float]):
        self.cfg = VolConfig(
            target_annualized=cfg["vol_target"]["target_annualized"],
            lookback_bars=cfg["vol_target"]["lookback_bars"],
            ewma_lambda=cfg["vol_target"]["ewma_lambda"],
            atr_n=cfg["vol_target"]["atr_n"],
            risk_bps_min=cfg["vol_target"]["risk_bps_bounds"]["min"],
            risk_bps_max=cfg["vol_target"]["risk_bps_bounds"]["max"],
        )
        self.atr_multiple_map = cfg["vol_target"]["atr_multiple"]
        self.tick_sizes = tick_sizes
        self.k = cfg.get("vol_target_k", 1.0)  # populated by calibrator

    def plan(self, symbol: str, equity: float, price: float, sigma_ann: float, atr: float) -> Tuple[float, int, float]:
        tick = float(self.tick_sizes.get(symbol, self.tick_sizes.get("default", 0.01)))
        mult = float(self.atr_multiple_map.get(symbol, self.atr_multiple_map.get("default", 2.5)))
        stop_ticks = stop_distance_ticks_for_symbol(symbol, atr, tick, mult)
        stop_price_distance = stop_ticks * tick
        qty, risk_bps = size_order_from_risk(equity, stop_price_distance, sigma_ann, self.cfg, self.k)
        return qty, stop_ticks, risk_bps

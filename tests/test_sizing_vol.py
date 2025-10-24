import math
from sizing.vol_target import stop_distance_ticks_for_symbol, size_order_from_risk, VolConfig


def test_stop_ticks_rounds_up():
    ticks = stop_distance_ticks_for_symbol("BTC/USDT", atr=100.0, tick_size=0.5, atr_multiple=2.0)
    assert ticks == math.ceil((2.0 * 100.0) / 0.5)


def test_qty_scales_with_vol():
    cfg = VolConfig()
    # higher sigma reduces risk_bps and qty
    q_low, r_low = size_order_from_risk(100000, 10.0, sigma_ann=0.10, cfg=cfg, k=1.0)
    q_high, r_high = size_order_from_risk(100000, 10.0, sigma_ann=0.40, cfg=cfg, k=1.0)
    assert r_low > r_high
    assert q_low > q_high

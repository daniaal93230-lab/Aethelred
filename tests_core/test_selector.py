from strategy.selector import pick_by_regime
from strategy.ema_trend import signal as sig_trend
from strategy.rsi_mean_revert import signal as sig_mr


def test_pick_by_regime_routing():
    name, fn = pick_by_regime("trend")
    assert name == "ema_trend"
    assert fn is sig_trend
    name, fn = pick_by_regime("chop")
    assert name == "rsi_mean_revert"
    assert fn is sig_mr
    name, fn = pick_by_regime("panic")
    assert name == "blocked"
    assert callable(fn)

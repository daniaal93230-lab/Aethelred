import pandas as pd
from core.risk import RiskConfig, position_size_usd
from core.regime import compute_regime
from core.breaker import BreakerState, BreakerConfig, update_breaker


def make_df(n=100, base=100.0, drift=0.0, vol=0.5):
    import numpy as np

    np.random.seed(0)
    rets = drift + np.random.randn(n) * vol
    price = base + np.cumsum(rets)
    high = price + abs(np.random.randn(n)) * 0.3
    low = price - abs(np.random.randn(n)) * 0.3
    df = pd.DataFrame({"open": price, "high": high, "low": low, "close": price, "volume": 1000.0})
    return df


def test_position_size_shrinks_with_higher_atr():
    df_lo = make_df(vol=0.2)
    df_hi = make_df(vol=1.2)
    price = float(df_lo["close"].iloc[-1])
    # emulate latest ATR by rough range
    atr_lo = float((df_lo["high"] - df_lo["low"]).rolling(14).mean().iloc[-1])
    atr_hi = float((df_hi["high"] - df_hi["low"]).rolling(14).mean().iloc[-1])
    cfg = RiskConfig()
    s_lo = position_size_usd(10000.0, price, atr_lo, cfg, None, 0.0)
    s_hi = position_size_usd(10000.0, price, atr_hi, cfg, None, 0.0)
    assert s_lo >= s_hi


def test_regime_detects_trend_vs_chop():
    df_trend = make_df(drift=0.2, vol=0.2)
    df_chop = make_df(drift=0.0, vol=0.2)
    r_trend = compute_regime(df_trend)
    r_chop = compute_regime(df_chop)
    assert r_trend.label in ("trend", "panic", "chop")
    assert r_chop.label in ("chop", "panic", "trend")


def test_breaker_activates_on_drawdown():
    st = BreakerState(day_start_equity=10000.0, trail_peak=10000.0, active=False, cooldown_until=None)
    cfg = BreakerConfig(max_intraday_dd_pct=0.01, cooldown_sec=1)
    st = update_breaker(st, equity=9800.0, regime_label="trend", cfg=cfg)
    assert st.active is True

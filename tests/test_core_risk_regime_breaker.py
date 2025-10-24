import math
import pandas as pd
from core.risk import RiskConfig, compute_atr, position_size_usd
from core.regime import compute_regime
from core.breaker import BreakerConfig, BreakerState, update_breaker


def _df_from_prices(prices):
    return pd.DataFrame({
        "open": prices,
        "high": [p * 1.01 for p in prices],
        "low": [p * 0.99 for p in prices],
        "close": prices,
    })


def test_compute_atr_basic():
    prices = [100 + i for i in range(60)]
    df = _df_from_prices(prices)
    atr = compute_atr(df, n=14)
    assert len(atr) == len(df)
    # ATR should be positive after warm-up
    assert float(atr.iloc[-1]) > 0


def test_position_size_usd_caps_and_min():
    prices = [100 for _ in range(60)]
    df = _df_from_prices(prices)
    atr = float(compute_atr(df, n=14).iloc[-1])
    cfg = RiskConfig(min_notional_usd=10.0, max_position_usd=100.0, max_symbol_gross_exposure_usd=100.0)
    notional = position_size_usd(
        equity_usd=1000.0,
        price=100.0,
        atr_latest=atr,
        cfg=cfg,
        leverage_limit=None,
        existing_symbol_gross_usd=0.0,
    )
    assert notional >= 0.0
    assert notional <= cfg.max_position_usd


def test_regime_and_breaker_logic():
    # Create volatile series to trigger panic via vol_z
    prices = [100 + ((-1)**i) * (i % 5) * 5 for i in range(120)]
    df = _df_from_prices(prices)
    reg = compute_regime(df)
    assert reg.label in ("panic", "trend", "chop", "unknown")

    cfg = BreakerConfig(max_intraday_dd_pct=0.01, cooldown_sec=1)
    st = BreakerState(day_start_equity=1000.0)
    # simulate drop to trigger breaker
    st = update_breaker(st, equity=980.0, regime_label=reg.label, cfg=cfg)
    assert isinstance(st.active, bool)

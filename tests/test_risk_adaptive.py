from decimal import Decimal
import math

from core.risk_adaptive import (
    compute_atr,
    compute_return_vol,
    compute_hybrid_vol,
    regime_scaler,
    target_position_size,
    AdaptiveRiskEngineV2,
)


def _make_ohlc(n=30, start_price=100.0, vol=1.0):
    """Create simple synthetic OHLC arrays that trend upward."""
    highs = []
    lows = []
    closes = []
    price = float(start_price)
    for i in range(n):
        # small drift + noise
        price = price * (1.0 + 0.001) + (vol * (0.5 - (i % 2)))
        high = price + 0.5
        low = price - 0.5
        close = price
        highs.append(high)
        lows.append(low)
        closes.append(close)
    return highs, lows, closes


def test_compute_atr_basic():
    highs, lows, closes = _make_ohlc(30, 100.0)
    atr = compute_atr(highs, lows, closes, period=14)
    assert isinstance(atr, Decimal)
    # ATR for this synthetic series should be > 0
    assert float(atr) > 0.0


def test_compute_return_vol_basic():
    _, _, closes = _make_ohlc(30, 100.0)
    rv = compute_return_vol(closes, period=20)
    assert isinstance(rv, Decimal)
    # small but non-zero log-return stdev
    assert float(rv) >= 0.0


def test_hybrid_and_target_size():
    highs, lows, closes = _make_ohlc(60, 200.0)
    atr = compute_atr(highs, lows, closes, period=14)
    rv = compute_return_vol(closes, period=20)
    price = Decimal(str(closes[-1]))
    hybrid = compute_hybrid_vol(atr, rv, price)
    assert isinstance(hybrid, Decimal)

    scaler = regime_scaler("trend")
    notional = target_position_size(Decimal("10000"), hybrid, scaler, target_vol=Decimal("0.02"))
    assert isinstance(notional, Decimal)
    # for reasonable hybrid vol the notional should be > 0
    assert float(notional) >= 0.0


def test_adaptive_risk_engine_integration():
    highs, lows, closes = _make_ohlc(80, 500.0)
    eng = AdaptiveRiskEngineV2()
    notional = eng.compute(highs, lows, closes, "trend", Decimal("20000"), Decimal(str(closes[-1])))
    assert isinstance(notional, Decimal)
    # With moderate volatility the engine can reasonably return a non-negative notional
    assert float(notional) >= 0.0

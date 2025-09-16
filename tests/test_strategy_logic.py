import random
import pytest
from strategy.trade_logic import TradeLogic, simple_moving_average_strategy

def test_random_signal_keys():
    logic = TradeLogic(mode="random")
    signal = logic.generate_signal("BTC/USDT")

    assert isinstance(signal, dict)
    assert "symbol" in signal
    assert "action" in signal
    assert "confidence" in signal

    assert signal["symbol"] == "BTC/USDT"
    assert signal["action"] in ["buy", "sell", "hold"]
    assert 0.4 <= signal["confidence"] <= 1.0

def test_sma_strategy_buy_signal():
    # SMA 3 > SMA 5 → buy
    ohlcv = [
        [0, 0, 0, 0, 100],
        [0, 0, 0, 0, 102],
        [0, 0, 0, 0, 104],
        [0, 0, 0, 0, 105],
        [0, 0, 0, 0, 108],
    ]
    assert simple_moving_average_strategy(ohlcv) == "buy"

def test_sma_strategy_sell_signal():
    # SMA 3 < SMA 5 → sell
    ohlcv = [
        [0, 0, 0, 0, 108],
        [0, 0, 0, 0, 105],
        [0, 0, 0, 0, 104],
        [0, 0, 0, 0, 102],
        [0, 0, 0, 0, 100],
    ]
    assert simple_moving_average_strategy(ohlcv) == "sell"

def test_sma_strategy_hold_signal():
    # SMA 3 == SMA 5 → hold
    ohlcv = [
        [0, 0, 0, 0, 100],
        [0, 0, 0, 0, 100],
        [0, 0, 0, 0, 100],
        [0, 0, 0, 0, 100],
        [0, 0, 0, 0, 100],
    ]
    assert simple_moving_average_strategy(ohlcv) == "hold"

def test_sma_strategy_insufficient_data():
    # Less than 5 candles → hold
    ohlcv = [
        [0, 0, 0, 0, 100],
        [0, 0, 0, 0, 101],
        [0, 0, 0, 0, 102],
    ]
    assert simple_moving_average_strategy(ohlcv) == "hold"

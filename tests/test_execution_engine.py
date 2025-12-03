import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from unittest.mock import patch
from core.execution_engine import ExecutionEngine


@pytest.fixture
def engine():
    return ExecutionEngine()


@patch("core.execution_engine.simple_moving_average_strategy")
@patch("core.execution_engine.Exchange.fetch_ohlcv")
@patch("core.execution_engine.DBManager.insert_trade")
def test_run_once_buy_signal(mock_insert, mock_fetch, mock_strategy, engine):
    mock_fetch.return_value = [
        [0, 0, 0, 0, 100],
        [0, 0, 0, 0, 105],
        [0, 0, 0, 0, 110],
        [0, 0, 0, 0, 115],
        [0, 0, 0, 0, 120],
    ]
    mock_strategy.return_value = "buy"

    engine.run_once(is_mock=True)

    mock_insert.assert_called_once()
    args = mock_insert.call_args[1]
    assert args["side"] == "BUY"
    assert args["symbol"] == "BTC/USDT"
    assert args["status"] == "FILLED"
    assert args["is_mock"] == 1


@patch("core.execution_engine.simple_moving_average_strategy")
@patch("core.execution_engine.Exchange.fetch_ohlcv")
@patch("core.execution_engine.DBManager.insert_trade")
def test_run_once_sell_signal(mock_insert, mock_fetch, mock_strategy, engine):
    mock_fetch.return_value = [
        [0, 0, 0, 0, 120],
        [0, 0, 0, 0, 115],
        [0, 0, 0, 0, 110],
        [0, 0, 0, 0, 105],
        [0, 0, 0, 0, 100],
    ]
    mock_strategy.return_value = "sell"

    engine.run_once(is_mock=True)

    mock_insert.assert_called_once()
    args = mock_insert.call_args[1]
    assert args["side"] == "SELL"


@patch("core.execution_engine.simple_moving_average_strategy")
@patch("core.execution_engine.Exchange.fetch_ohlcv")
@patch("core.execution_engine.DBManager.insert_trade")
def test_run_once_hold_signal(mock_insert, mock_fetch, mock_strategy, engine):
    mock_fetch.return_value = [[0, 0, 0, 0, 100]] * 5
    mock_strategy.return_value = "hold"

    engine.run_once(is_mock=True)

    mock_insert.assert_not_called()


@patch("core.execution_engine.Exchange.fetch_ohlcv")
def test_run_once_no_data(mock_fetch, engine):
    mock_fetch.return_value = []

    engine.run_once(is_mock=True)

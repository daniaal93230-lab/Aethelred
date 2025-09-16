import os
import sqlite3
import pytest
from db.db_manager import DBManager

@pytest.fixture(scope="function")
def test_db():
    # Setup: create a test DB
    db = DBManager(db_path="test_trades.db")
    yield db
    # Teardown: close and delete test DB
    db.close()
    os.remove("test_trades.db")

def test_insert_and_fetch_trade(test_db):
    trade_id = "test123"
    test_db.insert_trade(
        trade_id=trade_id,
        symbol="BTC/USDT",
        side="BUY",
        price=40000.0,
        amount=0.01,
        status="filled",
        is_mock=1
    )
    trades = test_db.fetch_all_trades()
    assert len(trades) == 1
    inserted = trades[0]
    assert inserted[1] == trade_id
    assert inserted[3] == "BTC/USDT"
    assert inserted[4] == "buy"
    assert inserted[5] == 40000.0
    assert inserted[6] == 0.01
    assert inserted[7] == "filled"
    assert inserted[8] == 1

def test_duplicate_trade_id_ignored(test_db):
    trade_id = "duplicate_test"
    test_db.insert_trade(
        trade_id=trade_id,
        symbol="BTC/USDT",
        side="SELL",
        price=42000.0,
        amount=0.02,
        status="filled",
        is_mock=1
    )
    # Insert same trade ID again
    test_db.insert_trade(
        trade_id=trade_id,
        symbol="BTC/USDT",
        side="SELL",
        price=42000.0,
        amount=0.02,
        status="filled",
        is_mock=1
    )

    trades = test_db.fetch_all_trades()
    assert len(trades) == 1  # Only one should be inserted

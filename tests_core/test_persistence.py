from core.persistence import init_db, record_equity, record_trade, recent_stats_7d, DB_PATH
from datetime import datetime, timezone
import os


def test_record_equity_creates_db_and_writes():
    if DB_PATH.exists():
        os.remove(DB_PATH)
    init_db()
    assert DB_PATH.exists()
    record_equity(12345.67)
    # if it didn't raise, it's good enough for this smoke check
    s = recent_stats_7d()
    assert isinstance(s, dict)


def test_recent_stats_from_trades():
    # ensure DB exists
    init_db()
    now = datetime.now(timezone.utc).isoformat()
    t1 = {
        "trade_id": f"T-{now}-1",
        "symbol": "BTC/USDT",
        "side": "buy",
        "qty": 0.01,
        "price": 60000.0,
        "pnl": 10.0,
        "entry_ts": now,
        "exit_ts": now,
    }
    t2 = {
        "trade_id": f"T-{now}-2",
        "symbol": "ETH/USDT",
        "side": "sell",
        "qty": 0.1,
        "price": 3000.0,
        "pnl": -5.0,
        "entry_ts": now,
        "exit_ts": now,
    }
    record_trade(t1)
    record_trade(t2)
    s = recent_stats_7d()
    assert s["trades_last_7d"] >= 2
    assert 0.0 <= s["winrate_7d"] <= 1.0

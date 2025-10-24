import os
import time
import sqlite3
from typing import Dict

from db.db_manager import DB_PATH, init_db, _get_conn
from bot.exchange import PaperExchange


def reset_db(starting_cash: float = 10000.0):
    init_db()
    with _get_conn() as con:
        cur = con.cursor()
        # Clean tables for a deterministic run
        try:
            cur.execute("DELETE FROM paper_positions")
        except Exception:
            pass
        try:
            cur.execute("DELETE FROM paper_trades")
        except Exception:
            pass
        try:
            cur.execute("DELETE FROM equity_snapshots")
        except Exception:
            pass
        # Reset paper_account row
        cur.execute(
            "UPDATE paper_account SET cash=?, equity=0, updated_ts=strftime('%s','now') WHERE id=1",
            (float(starting_cash),),
        )
        con.commit()


def run_scenario() -> Dict[str, float]:
    ex = PaperExchange(
        fees_bps=float(os.getenv("FEES_BPS", 7)),
        slippage_bps=float(os.getenv("SLIPPAGE_BPS", 5)),
        timeframe=os.getenv("TIMEFRAME", "15m"),
    )
    symbol = os.getenv("SYMBOL", "BTC/USDT")

    # Open a position: buy $1000 at price 100
    ex.buy_notional(symbol, 1000.0, last_price=100.0)

    # MTM at initial price
    snap1 = ex.account_overview({symbol: 100.0})
    time.sleep(0.1)
    # MTM after a price move up 5% (no new trade)
    snap2 = ex.account_overview({symbol: 105.0})

    return {
        "snap1_equity": float(snap1["equity"]),
        "snap2_equity": float(snap2["equity"]),
        "cash": float(snap2["cash"]),
    }


def print_sql_probes():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    print("\n-- side correctness and opened_ts persistence on adds vs flips")
    try:
        cur.execute(
            "SELECT symbol, qty, side, opened_ts, last_update_ts, avg_price FROM paper_positions ORDER BY symbol;"
        )
        rows = cur.fetchall()
        for r in rows:
            print(r)
    except Exception as e:
        print("paper_positions query error:", e)

    print("\n-- equity MTM parity across restarts")
    try:
        cur.execute("SELECT equity, updated_ts FROM paper_account ORDER BY updated_ts DESC LIMIT 5;")
        print(cur.fetchall())
    except Exception as e:
        print("paper_account query error:", e)

    print("\n-- trades carry fees, slippage, run_id")
    try:
        cur.execute(
            "SELECT ts, symbol, side, qty, price, fee_usd, slippage_bps, run_id FROM paper_trades ORDER BY ts DESC LIMIT 10;"
        )
        for row in cur.fetchall():
            print(row)
    except Exception as e:
        print("paper_trades query error:", e)

    print("\n-- indices exist")
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'ix_%' ORDER BY name;")
        print([r[0] for r in cur.fetchall()])
    except Exception as e:
        print("indices query error:", e)

    con.close()


def main():
    print("DB_PATH=", DB_PATH)
    reset_db()
    res = run_scenario()
    print("\nScenario result:", res)
    print_sql_probes()


if __name__ == "__main__":
    main()

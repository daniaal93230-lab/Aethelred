import sqlite3
import os
import sys

# Ensure project root is on sys.path when running from tools/
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from db.db_manager import DB_PATH, init_db  # noqa: E402


def main():
    print("DB_PATH=", DB_PATH)
    init_db()
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    print("\n-- side correctness and opened_ts persistence on adds vs flips")
    try:
        cur.execute(
            "SELECT symbol, qty, side, opened_ts, last_update_ts, avg_price FROM paper_positions ORDER BY symbol;"
        )
        for row in cur.fetchall():
            print(row)
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


if __name__ == "__main__":
    main()

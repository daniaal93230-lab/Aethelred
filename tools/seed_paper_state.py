import os
import sys
import time

# Ensure project root on path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from db.db_manager import init_db, set_cash  # noqa: E402
from exchange import PaperExchange  # noqa: E402


def main():
    # Initialize DB and set a known cash balance
    init_db()
    set_cash(10000.0)

    ex = PaperExchange(fees_bps=0.0, slippage_bps=0.0, timeframe=os.getenv("TIMEFRAME", "15m"))
    symbol = os.getenv("ACCEPT_SYM", "BTC_USDT")

    # Seed one long position: buy $1000 at price 100 => qty 10
    ex.buy_notional(symbol, usd=1000.0, last_price=100.0)

    # Initial MTM at 100 then update to 102 without trades to verify equity moves
    ex.account_overview({symbol: 100.0})
    time.sleep(1.1)
    ex.account_overview({symbol: 102.0})

    print("Seeded position and MTM updates complete.")


if __name__ == "__main__":
    main()

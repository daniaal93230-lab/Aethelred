# runner.py

import time
import random
import logging
from db.db_manager import DBManager

# ---------------------------------------
# CONFIGURE LOGGING (better than print)
# ---------------------------------------
logging.basicConfig(
    level=logging.INFO,  # Levels: DEBUG, INFO, WARNING, ERROR
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ---------------------------------------
# INITIALISE DATABASE MANAGER
# ---------------------------------------
db = DBManager()

# ---------------------------------------
# MOCK SYMBOLS AND TRADE SIDES
# ---------------------------------------
symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
sides = ['buy', 'sell']

# ---------------------------------------
# TRADE COUNTER TO ENSURE UNIQUE ID
# ---------------------------------------
counter = 0

# ---------------------------------------
# MAIN LOOP TO SIMULATE TRADES
# ---------------------------------------
try:
    while True:
        # Increment the counter each time to make a unique ID
        counter += 1

        # -----------------------------------
        # GENERATE MOCK TRADE DATA
        # -----------------------------------
        symbol = random.choice(symbols)        # Random trading pair
        side = random.choice(sides)            # Random side
        price = round(random.uniform(1000, 40000), 2)  # Mock price
        quantity = round(random.uniform(0.001, 1.0), 4)  # Mock quantity
        status = 'FILLED'                      # Assume all trades fill
        is_mock = 1                             # 1 = simulated

        # Create a unique trade ID using timestamp + counter
        timestamp_ms = int(time.time() * 1000)
        trade_id = f"mock_{timestamp_ms}_{counter}"

        # -----------------------------------
        # INSERT TRADE INTO DATABASE
        # -----------------------------------
        db.insert_trade(trade_id, symbol, side, price, quantity, status, is_mock)

        # -----------------------------------
        # WAIT BEFORE NEXT TRADE (2s)
        # -----------------------------------
        time.sleep(2)

# ---------------------------------------
# HANDLE CTRL+C CLEANLY
# ---------------------------------------
except KeyboardInterrupt:
    logging.info("Trade simulation stopped by user.")
    db.close()

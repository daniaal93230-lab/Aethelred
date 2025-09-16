import sqlite3
from datetime import datetime
from utils.logger import get_logger

# Initialize logger for this module
logger = get_logger(__name__)


class DBManager:
    def __init__(self, db_path="trades.db"):
        """
        Initialize the database connection and create the trades table if it doesn't exist.
        """
        try:
            self.conn = sqlite3.connect(db_path)
            self.cursor = self.conn.cursor()
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_id TEXT UNIQUE,
                    timestamp TEXT DEFAULT (datetime('now')),
                    symbol TEXT NOT NULL,
                    side TEXT CHECK(side IN ('buy','sell')) NOT NULL,
                    price REAL NOT NULL,
                    amount REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'filled',
                    is_mock INTEGER NOT NULL DEFAULT 0
                )
            """)
            self.conn.commit()
            logger.info("Database initialized and trades table ready.")
        except sqlite3.Error as e:
            logger.error(f"Database initialization failed: {e}")

    def insert_trade(self, trade_id, symbol, side, price, amount, status="filled", is_mock=0):
        """
        Insert a trade into the database.
        """
        try:
            side_clean = side.lower()
            timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            self.cursor.execute(
                """
                INSERT OR IGNORE INTO trades
                (trade_id, symbol, side, price, amount, timestamp, status, is_mock)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (trade_id, symbol, side_clean, price, amount, timestamp, status, is_mock),
            )

            self.conn.commit()
            logger.info(f"Trade logged: {trade_id} | {side_clean.upper()} {amount} {symbol} at {price}")
        except sqlite3.IntegrityError as e:
            logger.warning(f"Failed to insert trade {trade_id} (duplicate or invalid data): {e}")
        except Exception as e:
            logger.error(f"Unexpected error during trade insertion: {e}")

    def fetch_all_trades(self):
        """
        Fetch all trades ordered by latest.
        """
        try:
            self.cursor.execute("SELECT * FROM trades ORDER BY timestamp DESC")
            trades = self.cursor.fetchall()
            logger.info(f"Fetched {len(trades)} trades from database.")
            return trades
        except Exception as e:
            logger.error(f"Error fetching trades: {e}")
            return []

    def close(self):
        """
        Close the database connection.
        """
        try:
            self.conn.close()
            logger.info("Database connection closed.")
        except Exception as e:
            logger.error(f"Error closing database: {e}")

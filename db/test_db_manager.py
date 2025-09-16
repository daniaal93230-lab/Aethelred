from db.db_manager import DBManager

# Initialize DB manager (creates trades.db with proper schema)
db = DBManager()

# Insert a mock trade record
db.insert_trade("mocktrade_001", "BTC/USDT", "BUY", 30000.5, 0.01, status="FILLED", is_mock=1)

# Insert a live trade record (example)
db.insert_trade("live_001", "ETH/USDT", "sell", 2100.75, 0.5, status="filled", is_mock=0)

# Fetch all trades and print them
trades = db.fetch_all_trades()
for trade in trades:
    print(trade)

db.close()

import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "data" / "ledger.db"
conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("PRAGMA table_info(trades)")
cols = cur.fetchall()
print("cols:", [c["name"] for c in cols])
cur.execute("SELECT count(*) as c FROM trades")
print("count:", cur.fetchone()["c"])
cur.execute("SELECT * FROM trades LIMIT 5")
for r in cur.fetchall():
    print(dict(r))
conn.close()

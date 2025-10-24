import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "data" / "ledger.db"
if not DB.exists():
    print("DB not found", DB)
    raise SystemExit(1)
conn = sqlite3.connect(str(DB))
cur = conn.cursor()
cur.execute("SELECT name, type, sql FROM sqlite_master WHERE type IN ('table','view') ORDER BY name;")
for name, typ, sql in cur.fetchall():
    print(name, typ)
conn.close()

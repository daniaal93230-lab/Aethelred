"""Export paper_trades and decisions tables from the local SQLite DB to CSV and JSONL files.
Usage: python scripts/export_db.py [out_dir]
"""

import sqlite3
import csv
import json
import sys
from pathlib import Path

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("exports_download")
OUT.mkdir(parents=True, exist_ok=True)
DB = Path(__file__).resolve().parents[1] / "data" / "ledger.db"

if not DB.exists():
    print("DB not found at", DB)
    raise SystemExit(1)

conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Export whichever of these tables exist in the DB.
WANTED = ["paper_trades", "trades", "decisions"]
TABLES = {}
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
existing = {r[0] for r in cur.fetchall()}
for name in WANTED:
    if name in existing:
        TABLES[name] = {
            "csv": OUT / f"{name}.csv",
            "jsonl": OUT / f"{name}.jsonl",
        }


for tbl, paths in TABLES.items():
    try:
        cur.execute(f"SELECT * FROM {tbl}")
    except Exception as e:
        print(f"Skipping {tbl}: {e}")
        continue
    rows = cur.fetchall()
    if not rows:
        print(f"No rows in {tbl}")
        continue
    # write CSV
    with open(paths["csv"], "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(rows[0].keys())
        for r in rows:
            writer.writerow([r[k] for k in r.keys()])
    # write JSONL
    with open(paths["jsonl"], "w", encoding="utf-8") as f:
        for r in rows:
            obj = {k: r[k] for k in r.keys()}
            f.write(json.dumps(obj, default=str) + "\n")

print("Exported:")
for tbl, paths in TABLES.items():
    for k, p in paths.items():
        if p.exists():
            print(" -", p)

conn.close()

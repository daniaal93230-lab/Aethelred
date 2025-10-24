import sqlite3
import csv
import json
from pathlib import Path

DB = Path("data/aethelred.sqlite")
OUT = Path("exports_download")
OUT.mkdir(exist_ok=True)


def dump_table_to_csv(conn, query, outpath):
    cur = conn.execute(query)
    rows = cur.fetchall()
    names = [d[0] for d in cur.description]
    with open(outpath, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(names)
        for r in rows:
            w.writerow(r)


def dump_table_to_jsonl(conn, query, outpath):
    cur = conn.execute(query)
    rows = cur.fetchall()
    names = [d[0] for d in cur.description]
    with open(outpath, "w", encoding="utf-8") as f:
        for r in rows:
            obj = {names[i]: r[i] for i in range(len(names))}
            f.write(json.dumps(obj, default=str) + "\n")


if not DB.exists():
    print("DB not found:", DB)
    raise SystemExit(1)

conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row

# paper_trades
try:
    dump_table_to_csv(conn, "select * from paper_trades order by ts asc", OUT / "trades.csv")
    dump_table_to_jsonl(conn, "select * from paper_trades order by ts asc", OUT / "trades.jsonl")
    print("Wrote trades.csv, trades.jsonl")
except Exception as e:
    print("Failed paper_trades dump:", e)

# decision_log
try:
    dump_table_to_csv(conn, "select * from decision_log order by ts asc", OUT / "decisions.csv")
    dump_table_to_jsonl(conn, "select * from decision_log order by ts asc", OUT / "decisions.jsonl")
    print("Wrote decisions.csv, decisions.jsonl")
except Exception as e:
    print("Failed decision_log dump:", e)

conn.close()

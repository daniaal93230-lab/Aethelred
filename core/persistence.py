from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import os
from typing import Optional, Dict, Any
import sqlite3
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
# Default DB under project data/, but allow override via AET_DB_PATH
_default_db = ROOT / "data" / "aethelred.sqlite"
DB_PATH = Path(os.getenv("AET_DB_PATH", str(_default_db)))
DB_PATH.parent.mkdir(exist_ok=True)

_DDL = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS equities (
  ts TEXT NOT NULL,         -- ISO UTC
  equity REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS trades (
  trade_id TEXT PRIMARY KEY, -- caller ensures uniqueness (e.g. symbol+ts)
  symbol TEXT NOT NULL,
  side TEXT NOT NULL,        -- 'buy' or 'sell'
  qty REAL NOT NULL,
  price REAL NOT NULL,
  pnl REAL,                  -- optional until closed
  entry_ts TEXT NOT NULL,    -- ISO UTC
  exit_ts TEXT               -- ISO UTC when closed
);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys=ON;")
    return con


def init_db() -> None:
    con = _connect()
    try:
        con.executescript(_DDL)
        con.commit()
    finally:
        con.close()


def record_equity(equity: float, ts_iso: Optional[str] = None) -> None:
    """
    Append a single equity snapshot. Safe if DB is missing (creates).
    """
    init_db()
    ts = ts_iso or _now_iso()
    con = _connect()
    try:
        con.execute("INSERT INTO equities(ts, equity) VALUES(?,?)", (ts, float(equity)))
        con.commit()
    finally:
        con.close()


def record_trade(trade: Dict[str, Any]) -> None:
    """
    Insert or replace a trade row.
    Expected keys: trade_id, symbol, side, qty, price, entry_ts, [pnl, exit_ts]
    """
    init_db()
    con = _connect()
    try:
        con.execute(
            """INSERT OR REPLACE INTO trades
               (trade_id, symbol, side, qty, price, pnl, entry_ts, exit_ts)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                str(trade["trade_id"]),
                str(trade["symbol"]),
                str(trade["side"]),
                float(trade["qty"]),
                float(trade["price"]),
                None if trade.get("pnl") is None else float(trade["pnl"]),
                str(trade.get("entry_ts") or _now_iso()),
                trade.get("exit_ts"),
            ),
        )
        con.commit()
    finally:
        con.close()

def open_trade_if_none(symbol: str, side: str, qty: float, price: float,
                       trade_id: Optional[str] = None, entry_ts: Optional[str] = None) -> str:
    """
    Open a trade only if there is no open trade (pnl IS NULL) for this symbol.
    Returns the trade_id used.
    """
    init_db()
    tid = trade_id or f"{symbol}-{side}-{_now_iso()}"
    ts = entry_ts or _now_iso()
    con = _connect()
    try:
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM trades WHERE symbol=? AND pnl IS NULL", (symbol,))
        if int(cur.fetchone()[0] or 0) > 0:
            return tid
        cur.execute(
            """INSERT OR REPLACE INTO trades(trade_id, symbol, side, qty, price, pnl, entry_ts, exit_ts)
               VALUES(?,?,?,?,?,?,?,?)""",
            (tid, symbol, side, float(qty), float(price), None, ts, None),
        )
        con.commit()
        return tid
    finally:
        con.close()

def close_trade_for_symbol(symbol: str, exit_price: float, exit_ts: Optional[str] = None) -> Optional[float]:
    """
    Close the most-recent open trade for this symbol (pnl IS NULL). Computes PnL for long only.
    Returns pnl or None if no open trade.
    """
    init_db()
    ts = exit_ts or _now_iso()
    con = _connect()
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT trade_id, side, qty, price FROM trades WHERE symbol=? AND pnl IS NULL ORDER BY entry_ts DESC LIMIT 1",
            (symbol,),
        )
        row = cur.fetchone()
        if not row:
            return None
        tid, side, qty, entry_price = row
        qty = float(qty); entry_price = float(entry_price)
        # Long-only pnl; extend later for shorts if enabled
        pnl = (float(exit_price) - entry_price) * qty if side.lower() == "buy" else (entry_price - float(exit_price)) * qty
        cur.execute("UPDATE trades SET pnl=?, exit_ts=? WHERE trade_id= ?", (float(pnl), ts, tid))
        con.commit()
        return float(pnl)
    finally:
        con.close()

def recent_stats_7d() -> Dict[str, float]:
    """
    Compute simple stats from trades over the last 7 days:
      winrate_7d, expectancy_7d_usd, trades_last_7d
    Only includes rows with non-null pnl.
    """
    if not DB_PATH.exists():
        return {"winrate_7d": 0.0, "expectancy_7d_usd": 0.0, "trades_last_7d": 0}
    con = _connect()
    try:
        cur = con.cursor()
        cur.execute(
            """
            SELECT
              COUNT(*) as n,
              AVG(pnl) as avg_pnl,
              SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as winrate
            FROM trades
            WHERE pnl IS NOT NULL
              AND datetime(entry_ts) >= datetime('now','-7 day')
            """
        )
        row = cur.fetchone()
        if not row or row[0] is None:
            return {"winrate_7d": 0.0, "expectancy_7d_usd": 0.0, "trades_last_7d": 0}
        n = int(row[0] or 0)
        winrate = float(row[2] or 0.0) if n > 0 else 0.0
        avg = float(row[1] or 0.0) if n > 0 else 0.0
        return {"winrate_7d": winrate, "expectancy_7d_usd": avg, "trades_last_7d": n}
    finally:
        con.close()

def load_equity_series(limit: int = 2000) -> list[tuple[str, float]]:
    """
    Return up to `limit` points of (ts_iso, equity) ordered by ts ascending.
    If DB missing or empty, return [].
    """
    if not DB_PATH.exists():
        return []
    con = _connect()
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT ts, equity FROM equities ORDER BY datetime(ts) ASC LIMIT ?",
            (int(limit),),
        )
        rows = cur.fetchall() or []
        # ensure types are correct
        out = []
        for ts, eq in rows:
            try:
                out.append((str(ts), float(eq)))
            except Exception:
                continue
        return out
    finally:
        con.close()

from fastapi import APIRouter, Response, HTTPException
import sqlite3
import csv
import io
from db.db_manager import get_db_path, table_exists

router = APIRouter()


def _rows_to_csv(headers, rows) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(headers)
    for r in rows:
        writer.writerow([r.get(h) for h in headers])
    return buf.getvalue().encode("utf-8")


def _fetch_all(q: str, params: tuple = ()) -> list[dict]:
    db_path = get_db_path()
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute(q, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        con.close()


@router.get("/trades.csv")
def export_trades_csv():
    """
    Defensive exporter.
    Works if DB has either:
      - paper_trades(ts, symbol, side, qty, entry, exit, pnl, pnl_pct, hold_s, ...), or
      - trades(pair, side, entry_ts, exit_ts, entry, exit, pnl, pnl_pct, hold_s)
    Uses a compat view if present.
    """
    # Prefer compat view if present, but it may be stale/broken; defend against OperationalError
    if table_exists("v_trades_compat"):
        try:
            rows = _fetch_all("SELECT * FROM v_trades_compat ORDER BY ts ASC")
            if not rows:
                return Response(
                    content=_rows_to_csv(
                        list(["ts", "symbol", "side", "qty", "entry", "exit", "pnl", "pnl_pct", "hold_s"]), []
                    ),
                    media_type="text/csv",
                )
            headers = list(rows[0].keys())
            return Response(content=_rows_to_csv(headers, rows), media_type="text/csv")
        except sqlite3.OperationalError:
            # Fall through to explicit table queries below
            pass

    # Else choose best available source
    if table_exists("paper_trades"):
        # Select everything and map defensively in Python to avoid SQL errors on missing columns
        raw = _fetch_all("SELECT * FROM paper_trades ORDER BY ts ASC")
        rows = []
        for r in raw:
            mapped = {
                "ts": r.get("ts") or r.get("entry_ts") or r.get("timestamp"),
                "symbol": r.get("symbol") or r.get("pair"),
                "side": r.get("side"),
                "qty": r.get("qty") or r.get("quantity"),
                "entry": r.get("entry") or r.get("price") or r.get("entry_price"),
                "exit": r.get("exit") or r.get("exit_price") or None,
                "pnl": r.get("pnl") or r.get("pnl_usd") or 0,
                "pnl_pct": r.get("pnl_pct") or 0,
                "hold_s": r.get("hold_s") or 0,
            }
            rows.append(mapped)
    elif table_exists("trades"):
        raw = _fetch_all("SELECT * FROM trades ORDER BY COALESCE(entry_ts, ts) ASC")
        rows = []
        for r in raw:
            mapped = {
                "ts": r.get("entry_ts") or r.get("ts") or r.get("timestamp"),
                "symbol": r.get("pair") or r.get("symbol"),
                "side": r.get("side"),
                "qty": r.get("qty") or r.get("quantity") or r.get("amount") or None,
                "entry": r.get("entry") or r.get("price") or None,
                "exit": r.get("exit") or r.get("exit_price") or None,
                "pnl": r.get("pnl") or r.get("pnl_usd") or 0,
                "pnl_pct": r.get("pnl_pct") or 0,
                "hold_s": r.get("hold_s") or 0,
            }
            rows.append(mapped)
    else:
        raise HTTPException(status_code=404, detail="No trades table found")

    headers = ["ts", "symbol", "side", "qty", "entry", "exit", "pnl", "pnl_pct", "hold_s"]
    return Response(content=_rows_to_csv(headers, rows), media_type="text/csv")


@router.get("/decisions.csv")
def export_decisions_csv():
    """
    Handles both decisions and decision_log styles.
    Expected columns (mapped defensively):
      ts, symbol, raw_signal, final_action, veto_reason, model_version, features_hash
    """
    if table_exists("v_decisions_compat"):
        rows = _fetch_all("SELECT * FROM v_decisions_compat ORDER BY ts ASC")
        headers = (
            list(rows[0].keys())
            if rows
            else ["ts", "symbol", "raw_signal", "final_action", "veto_reason", "model_version", "features_hash"]
        )
        return Response(content=_rows_to_csv(headers, rows), media_type="text/csv")

    # try decisions
    rows = []
    if table_exists("decisions"):
        rows = _fetch_all("""
            SELECT
              COALESCE(ts, timestamp) AS ts,
              symbol,
              COALESCE(raw_signal, signal) AS raw_signal,
              COALESCE(final_action, action) AS final_action,
              COALESCE(veto_reason, reason) AS veto_reason,
              COALESCE(model_version, '') AS model_version,
              COALESCE(features_hash, '') AS features_hash
            FROM decisions
            ORDER BY COALESCE(ts, timestamp) ASC
        """)
    elif table_exists("decision_log"):
        rows = _fetch_all("""
            SELECT
              COALESCE(ts, timestamp) AS ts,
              symbol,
              raw_signal,
              final_action,
              COALESCE(veto_reason, reason) AS veto_reason,
              COALESCE(model_version, '') AS model_version,
              COALESCE(features_hash, '') AS features_hash
            FROM decision_log
            ORDER BY COALESCE(ts, timestamp) ASC
        """)
    else:
        # No decisions at all; return empty CSV with headers
        headers = ["ts", "symbol", "raw_signal", "final_action", "veto_reason", "model_version", "features_hash"]
        return Response(content=_rows_to_csv(headers, []), media_type="text/csv")

    headers = ["ts", "symbol", "raw_signal", "final_action", "veto_reason", "model_version", "features_hash"]
    return Response(content=_rows_to_csv(headers, rows), media_type="text/csv")

from fastapi import APIRouter, Response, HTTPException
import sqlite3
import csv
import io
from collections import defaultdict
from db.db_manager import get_db_path, table_exists
from api.contracts.decisions_header import DECISIONS_HEADER

router = APIRouter(prefix="/export", tags=["export"]) if False else APIRouter()

# DECISIONS_HEADER now centralized in api.contracts.decisions_header


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
    # Prefer compat view if present
    if table_exists("v_decisions_compat"):
        try:
            rows = _fetch_all("SELECT * FROM v_decisions_compat ORDER BY ts ASC")
        except sqlite3.OperationalError:
            rows = []
        # If view exists and rows present, just return as-is but ensure header mapping
        if rows:
            headers = list(rows[0].keys())
            return Response(content=_rows_to_csv(headers, rows), media_type="text/csv")

    # Try conventional tables and remap defensively in Python
    rows = []
    if table_exists("decisions"):
        try:
            raw = _fetch_all("SELECT * FROM decisions ORDER BY ts ASC")
        except Exception:
            raw = []
    elif table_exists("decision_log"):
        try:
            raw = _fetch_all("SELECT * FROM decision_log ORDER BY ts ASC")
        except Exception:
            raw = []
    else:
        raw = []

    # Emit canonical header
    sio = io.StringIO()
    w = csv.writer(sio)
    w.writerow(DECISIONS_HEADER)
    # First pass: normalize rows with defensive mapping
    norm = []
    for r in raw:
        d = dict(r)
        norm.append(
            {
                "ts": d.get("ts") or d.get("time") or d.get("entry_ts"),
                "symbol": d.get("symbol") or d.get("pair") or d.get("instrument"),
                "regime": d.get("regime") or d.get("market_regime") or "unknown",
                "strategy_name": d.get("strategy_name") or d.get("strategy") or d.get("strat") or "unknown",
                "signal_side": d.get("signal_side")
                or d.get("strategy_side")
                or d.get("side_raw")
                or d.get("side")
                or "HOLD",
                "signal_strength": d.get("signal_strength") or d.get("strength") or 0.0,
                "signal_stop_hint": d.get("signal_stop_hint") or d.get("stop_hint"),
                "signal_ttl": d.get("signal_ttl") or d.get("ttl"),
                "final_action": d.get("final_action") or d.get("action") or d.get("decision"),
                "final_size": d.get("final_size") or d.get("size") or d.get("qty"),
                "veto_ml": d.get("veto_ml"),
                "veto_risk": d.get("veto_risk"),
                "veto_reason": d.get("veto_reason") or d.get("reason"),
                "price": d.get("price") or d.get("fill_price") or d.get("px"),
                "note": d.get("note") or d.get("comment"),
            }
        )
    # Second pass: coalesce by (ts,symbol) preferring last non-null for final_* and veto_* fields
    bucket = defaultdict(lambda: {k: None for k in DECISIONS_HEADER})
    order = []  # preserve first-seen order
    for row in norm:
        key = (row["ts"], row["symbol"])
        if key not in bucket:
            order.append(key)
            bucket[key].update(row)
        else:
            merged = bucket[key]
            merged["regime"] = row.get("regime") or merged["regime"]
            merged["strategy_name"] = row.get("strategy_name") or merged["strategy_name"]
            for k in ["signal_side", "signal_strength", "signal_stop_hint", "signal_ttl", "price", "note"]:
                merged[k] = row.get(k) if row.get(k) is not None else merged[k]
            for k in ["final_action", "final_size", "veto_ml", "veto_risk", "veto_reason"]:
                merged[k] = row.get(k) if row.get(k) is not None else merged[k]
    for key in order:
        row = bucket[key]
        w.writerow([row[k] for k in DECISIONS_HEADER])
    return Response(content=sio.getvalue(), media_type="text/csv")

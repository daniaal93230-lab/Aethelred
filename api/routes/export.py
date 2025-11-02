from fastapi import APIRouter, Response, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
import sqlite3
import csv
import io
from collections import defaultdict
from db.db_manager import get_db_path, table_exists
from api.contracts.decisions_header import DECISIONS_HEADER

TRADES_HEADER = [
    "ts_open",
    "ts_close",
    "symbol",
    "side",
    "qty",
    "entry",
    "exit",
    "pnl",
    "pnl_pct",
    "fee_usd",
    "slippage_bps",
    "note",
]

_KEY_ALIASES = {
    "ts_open": ["ts_open", "open_ts", "entry_ts", "opened_ts"],
    "ts_close": ["ts_close", "close_ts", "exit_ts", "closed_ts"],
    "symbol": ["symbol", "pair", "instrument"],
    "side": ["side", "position_side"],
    "qty": ["qty", "quantity", "size"],
    "entry": ["entry", "entry_price", "avg_entry"],
    "exit": ["exit", "exit_price", "avg_exit", "mark_exit"],
    "pnl": ["pnl", "pnl_usd", "profit"],
    "pnl_pct": ["pnl_pct", "return_pct", "ret_pct"],
    "fee_usd": ["fee_usd", "fees_usd", "commission_usd"],
    "slippage_bps": ["slippage_bps", "slip_bps", "slippage"],
    "note": ["note", "notes", "comment"],
}


def _coerce_row(row: dict) -> dict:
    """Map arbitrary engine row keys into TRADES_HEADER keys."""
    out = {}
    for k in TRADES_HEADER:
        val = None
        for alias in _KEY_ALIASES.get(k, [k]):
            if alias in row and row[alias] not in (None, ""):
                val = row[alias]
                break
        out[k] = val
    return out


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
def export_trades_csv(request: Request):
    """
    Streams trades from the engine store as CSV.
    No business logic duplication; relies on engine.iter_trades()
    which yields dicts with fields matching TRADES_HEADER.
    """
    eng = getattr(request.app.state, "engine", None)
    if eng is None:
        raise HTTPException(status_code=503, detail="Engine unavailable")

    def _gen():
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=TRADES_HEADER, extrasaction="ignore")
        writer.writeheader()
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)
        for row in eng.iter_trades():
            writer.writerow(row)
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    return StreamingResponse(_gen(), media_type="text/csv")


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


@router.get("/decisions.schema.json")
def export_decisions_schema():
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Aethelred Decisions CSV",
        "type": "object",
        "properties": {
            "ts": {"type": ["number", "string"]},
            "symbol": {"type": "string"},
            "regime": {"type": "string"},
            "strategy_name": {"type": "string"},
            "signal_side": {"type": "string", "enum": ["BUY", "SELL", "HOLD"]},
            "signal_strength": {"type": ["number", "null"], "minimum": 0.0, "maximum": 1.0},
            "signal_stop_hint": {"type": ["number", "null"]},
            "signal_ttl": {"type": ["integer", "null"], "minimum": 0},
            "final_action": {"type": ["string", "null"], "enum": ["BUY", "SELL", "HOLD", None]},
            "final_size": {"type": ["number", "null"]},
            "veto_ml": {"type": ["boolean", "null"]},
            "veto_risk": {"type": ["boolean", "null"]},
            "veto_reason": {"type": ["string", "null"]},
            "price": {"type": ["number", "null"]},
            "note": {"type": ["string", "null"]},
        },
        "required": DECISIONS_HEADER[:5],  # minimally ensure leading identifiers
        "additionalProperties": True,
    }
    return JSONResponse(schema)

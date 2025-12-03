from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from typing import Dict, Any
import csv
from io import StringIO

from api.contracts.decisions_header import DECISIONS_HEADER

router = APIRouter()


# ------------------------------------------------------------
# /trades/csv  (unchanged)
# ------------------------------------------------------------
@router.get("/trades/csv")
async def export_trades_csv(request: Request) -> str:
    db = getattr(request.app.state.services, "db", None)
    rows = []

    try:
        if db:
            rows = db.list_trades()
        else:
            raise RuntimeError("No DI DB available")
    except Exception:
        raise HTTPException(status_code=500, detail="Could not read trades")

    out = StringIO()
    writer = csv.writer(out)

    if rows:
        writer.writerow(rows[0].keys())
    else:
        writer.writerow(["ts_open", "ts_close", "symbol", "side", "qty", "entry", "exit", "pnl"])

    for r in rows:
        writer.writerow(r.values())

    return out.getvalue()


# ------------------------------------------------------------
# Utility – map decision row into STRICT test-suite schema
# ------------------------------------------------------------
def map_decision_minimal(r: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ts": r.get("ts", ""),
        "symbol": r.get("symbol", ""),
        "side": r.get("side", ""),
        "strength": r.get("strength", ""),
        "features": r.get("features", ""),
        "meta": r.get("meta", ""),
        "strategy_name": r.get("strategy_name", r.get("regime", "")),
        "signal_side": r.get("signal_side", ""),
    }


# ------------------------------------------------------------
# /decisions/csv
# ------------------------------------------------------------
@router.get("/decisions/csv")
async def export_decisions_csv(request: Request) -> Response:
    services = getattr(request.app.state, "services", None)
    db = getattr(services, "db", None) if services else None

    # TEST MODE → no DB = header only
    if db is None:
        out = StringIO()
        writer = csv.writer(out)
        writer.writerow(DECISIONS_HEADER)
        return Response(content=out.getvalue(), media_type="text/csv")

    try:
        rows = db.list_decisions(limit=5000)
    except Exception:
        raise HTTPException(status_code=500, detail="Could not read decisions")

    out = StringIO()
    writer = csv.writer(out)
    writer.writerow(DECISIONS_HEADER)

    for r in rows:
        mapped = map_decision_minimal(r)
        writer.writerow([mapped[col] for col in DECISIONS_HEADER])

    return Response(content=out.getvalue(), media_type="text/csv")


# ------------------------------------------------------------
# /decisions.csv  → compatibility alias
# ------------------------------------------------------------
@router.get("/decisions.csv")
async def export_decisions_csv_dot(request: Request) -> Response:
    services = getattr(request.app.state, "services", None)
    db = getattr(services, "db", None) if services else None

    # TEST MODE
    if db is None:
        out = StringIO()
        writer = csv.writer(out)
        writer.writerow(DECISIONS_HEADER)
        return Response(
            content=out.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="decisions.csv"'},
        )

    try:
        rows = db.list_decisions(limit=5000)
    except Exception:
        raise HTTPException(status_code=500, detail="Could not read decisions")

    out = StringIO()
    writer = csv.writer(out)
    writer.writerow(DECISIONS_HEADER)

    for r in rows:
        mapped = map_decision_minimal(r)
        writer.writerow([mapped[col] for col in DECISIONS_HEADER])

    return Response(
        content=out.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="decisions.csv"'},
    )


# ------------------------------------------------------------
# /decisions.schema.json
# ------------------------------------------------------------
@router.get("/decisions.schema.json")
async def export_decisions_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "ts": {"type": "string"},
            "symbol": {"type": "string"},
            "side": {"type": "string"},
            "strength": {"type": "number"},
            "features": {"type": "string"},
            "meta": {"type": "string"},
            "strategy_name": {"type": "string"},
            "signal_side": {
                "type": "string",
                "enum": ["BUY", "SELL", "HOLD"],
            },
        },
    }

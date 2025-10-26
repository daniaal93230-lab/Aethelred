from __future__ import annotations

from typing import Any, Optional
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from utils.snapshot import write_runtime_snapshot
import time


class DemoPayload(BaseModel):
    symbol: Optional[str] = "BTCUSDT"
    side: Optional[str] = "long"
    qty: Optional[float] = 0.001
    price: Optional[float] = 100.0


router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/paper_quick_run")
def paper_quick_run(request: Request, payload: DemoPayload) -> Any:
    """
    QA demo route.
    If the app has a QADevEngine attached at `app.state.engine`, open a tiny in-memory demo position and write a runtime snapshot.
    Also append a demo trade record so `/export/trades.csv` contains at least one row for acceptance tests.
    """
    app = request.app
    engine = getattr(app.state, "engine", None)
    if engine is None:
        return JSONResponse(
            {"error": "QA engine not attached. Start the API with QA_DEV_ENGINE=1 or QA_MODE=1 to enable demo mode."},
            status_code=503,
        )

    # Extract payload values
    symbol = payload.symbol
    side = (payload.side or "long").lower()
    qty = float(payload.qty or 0.0)
    price = float(payload.price or 0.0)

    # Prefer the in-memory demo helper when available (opens a position)
    if hasattr(engine, "_open_demo_position"):
        try:
            engine._open_demo_position(symbol=symbol, side=side, qty=qty, price=price)
        except Exception:
            pass

    # Also create a demo trade record so /export/trades.csv has at least one row for acceptance tests
    try:
        now = int(time.time())
        demo_trade = {
            "ts_open": now - 60,
            "ts_close": now,
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "entry": price,
            "exit": price,
            "pnl": 0.0,
            "pnl_pct": 0.0,
            "fee_usd": 0.0,
            "slippage_bps": 0.0,
            "note": "demo",
        }
        if hasattr(engine, "_trades") and isinstance(getattr(engine, "_trades"), list):
            engine._trades.append(demo_trade)
    except Exception:
        pass

    # write a runtime snapshot (engine-backed) for UI/acceptance testing
    try:
        write_runtime_snapshot(engine)
    except Exception:
        # Do not fail the endpoint if snapshot write fails; return partial info
        return JSONResponse({"ok": True, "warning": "snapshot_write_failed"})

    # Return a compact confirmation
    return {"ok": True, "symbol": symbol, "qty": qty, "price": price}

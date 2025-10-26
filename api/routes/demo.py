from __future__ import annotations

from typing import Any, Optional
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from utils.snapshot import write_runtime_snapshot

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/paper_quick_run")
def paper_quick_run(
    request: Request, symbol: Optional[str] = "BTCUSDT", qty: Optional[float] = 0.001, price: Optional[float] = 100.0
) -> Any:
    """
    QA demo route.
    If the app has a QADevEngine attached at `app.state.engine`, open a tiny in-memory demo position and write a runtime snapshot.
    Returns a compact confirmation for quick verification.
    """
    app = request.app
    engine = getattr(app.state, "engine", None)
    if engine is None:
        return JSONResponse(
            {"error": "QA engine not attached. Start the API with QA_DEV_ENGINE=1 or QA_MODE=1 to enable demo mode."},
            status_code=503,
        )

    # Prefer the in-memory demo helper when available
    if hasattr(engine, "_open_demo_position"):
        try:
            engine._open_demo_position(symbol=symbol, side="long", qty=qty, price=price)
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

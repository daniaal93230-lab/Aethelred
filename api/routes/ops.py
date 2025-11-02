from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()


def _engine(request: Request):
    eng = getattr(request.app.state, "engine", None)
    if eng is None:
        raise HTTPException(status_code=503, detail="Engine unavailable")
    return eng


@router.get("/healthz")
async def healthz(request: Request):
    """
    Liveness and engine heartbeat.
    Includes positions_count and last_tick_ts when available.
    """
    eng = getattr(request.app.state, "engine", None)
    status = {"api": "ok", "engine": "missing"}
    if eng is not None and hasattr(eng, "heartbeat"):
        try:
            hb = eng.heartbeat()
            # normalize common fields
            status["engine"] = {
                "ok": hb.get("ok", True),
                "positions_count": hb.get("positions_count", hb.get("positions", 0)),
                "last_tick_ts": hb.get("last_tick_ts", hb.get("ts")),
            }
        except Exception as e:
            status["engine"] = f"error: {e}"
    return status


@router.post("/flatten")
async def flatten_all(request: Request):
    """
    Idempotent flatten. Delegates to engine.
    """
    eng = _engine(request)
    try:
        result = await eng.flatten_all(reason="api_flatten")
        return {"ok": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class BreakerState(BaseModel):
    kill_switch: Optional[bool] = None
    manual_breaker: Optional[bool] = None
    clear_daily_loss: Optional[bool] = None


@router.get("/risk/breaker")
async def breaker_view(request: Request):
    eng = _engine(request)
    try:
        return {"ok": True, "breakers": eng.breakers_view()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/risk/breaker")
async def breaker_set(payload: BreakerState, request: Request):
    """
    Idempotent setter. Any None is ignored. Setting kill_switch True blocks new trades.
    clear_daily_loss True resets the tripped daily breaker after review.
    """
    eng = _engine(request)
    try:
        updated = eng.breakers_set(
            kill_switch=payload.kill_switch,
            manual_breaker=payload.manual_breaker,
            clear_daily_loss=payload.clear_daily_loss,
        )
        return {"ok": True, "breakers": updated}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

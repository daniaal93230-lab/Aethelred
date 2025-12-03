from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from ops.notifier import get_notifier

router = APIRouter(prefix="/ops")


@router.post("/alert")
async def send_alert(category: str, details: Dict[str, Any]):
    """
    Manually dispatch an ops alert.
    Useful for testing or orchestration tools.
    """
    try:
        get_notifier().send(category, **details)
    except Exception:
        # best-effort, do not raise
        pass
    return {"status": "ok", "category": category, "details": details}


def _services(request: Request):
    """
    Retrieve DI-attached services, raising structured 503 when unavailable.
    """
    services = getattr(request.app.state, "services", None)
    if services is None:
        raise HTTPException(status_code=503, detail="Services container unavailable")
    return services


def _engine(request: Request):
    """
    Retrieve DI-attached engine with consistent error messaging.
    """
    services = _services(request)
    eng = getattr(services, "engine", None)
    if eng is None:
        raise HTTPException(status_code=503, detail="Engine unavailable")
    return eng


@router.get("/healthz")
async def healthz(request: Request):
    """
    Liveness and engine heartbeat.
    Includes positions_count and last_tick_ts when available.
    """
    # DI lookup (health should degrade gracefully)
    try:
        services = _services(request)
        eng = getattr(services, "engine", None)
    except Exception:
        eng = None
    status = {"api": "ok", "engine": "missing"}
    if eng is not None and hasattr(eng, "heartbeat"):
        try:
            hb = eng.heartbeat()
            # normalize and enrich
            status["engine"] = {
                "ok": hb.get("ok", True),
                "positions_count": hb.get("positions_count", hb.get("positions", 0)),
                "last_tick_ts": hb.get("last_tick_ts", hb.get("ts")),
                "breakers": getattr(eng, "breakers_view", lambda: {})(),
                "ts": getattr(eng, "account_snapshot", lambda: {"ts": None})().get("ts"),
                "realized_pnl_today_usd": getattr(eng, "realized_pnl_today_usd", lambda: 0.0)(),
                "trade_count_today": getattr(eng, "trade_count_today", lambda: 0)(),
            }
        except Exception as e:
            status["engine"] = f"error: {e}"
    return status


@router.get("/ping")
async def ping() -> Dict[str, str]:
    """Simple connectivity check."""
    return {"status": "ok"}


@router.get("/signal")
async def get_signal(request: Request, symbol: str = "BTC/USDT") -> Dict[str, Any]:
    """
    Return a strategy signal for the given symbol.

    Query param `test=1` preserves legacy SMA test semantics (returns raw 'buy'/'sell'/'hold').
    In production this routes through the engine's strategy router and returns a typed view.
    """
    testing = request.query_params.get("test") == "1"

    # fetch ohlcv via engine or exchange
    try:
        eng = _engine(request)
    except Exception:
        raise HTTPException(status_code=503, detail="Engine unavailable")

    exch = getattr(eng, "exchange", None) or getattr(eng, "_exch", None)
    if exch is None:
        raise HTTPException(status_code=503, detail="Exchange unavailable")

    try:
        ohlcv = exch.fetch_ohlcv(symbol)
    except Exception:
        ohlcv = []

    if testing:
        try:
            from core.trade_logic import simple_moving_average_strategy

            raw = simple_moving_average_strategy(ohlcv)
            return {"mode": "test", "signal": raw}
        except Exception:
            raise HTTPException(status_code=500, detail="Test SMA failed")

    # production: prefer engine strategos if present
    strategos = getattr(eng, "_strategos", None) or getattr(eng, "strategos", None)
    if strategos is not None:
        try:
            typed = strategos.route(ohlcv)
            return {"side": typed.side.value.lower(), "strength": typed.strength, "ttl": typed.ttl}
        except Exception:
            raise HTTPException(status_code=500, detail="Strategy routing failed")

    # fallback: call SMA and wrap
    try:
        from core.trade_logic import simple_moving_average_strategy

        raw = simple_moving_average_strategy(ohlcv)
        return {"mode": "fallback", "signal": raw}
    except Exception:
        raise HTTPException(status_code=500, detail="No strategy available")


@router.get("/trades")
async def list_trades(request: Request) -> List[Dict[str, Any]]:
    """Return recorded trades via DI-attached DB service."""
    services = _services(request)
    db = getattr(services, "db", None)
    if db is None:
        raise HTTPException(status_code=503, detail="DB service unavailable")
    return db.list_trades()


@router.get("/decisions")
async def list_decisions(request: Request) -> List[Dict[str, Any]]:
    """Return recorded decisions via DI-attached DB service."""
    services = _services(request)
    db = getattr(services, "db", None)
    if db is None:
        raise HTTPException(status_code=503, detail="DB service unavailable")
    return db.list_decisions()


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

from fastapi import APIRouter, Request
from typing import Any, Dict
import asyncio

# All engine/exchange/db objects now come from DI (lifespan.py)
# No more direct construction or imports from core.engine, PaperExchange, etc.

router = APIRouter()

###############################################################################
# DI HELPERS
###############################################################################


def _get_engine(request: Request) -> Any:
    """Fetch the DI-injected trading engine."""
    return request.app.state.services.engine


def _get_loop_state(request: Request) -> bool:
    """Fetch or initialize loop running flag dynamically."""
    if not hasattr(request.app.state, "demo_loop_running"):
        request.app.state.demo_loop_running = False
    return bool(request.app.state.demo_loop_running)


@router.post("/demo/start")
async def start_demo(request: Request) -> Dict[str, Any]:
    running = _get_loop_state(request)
    if running:
        return {"status": "already_running"}

    request.app.state.demo_loop_running = True
    engine = _get_engine(request)
    asyncio.create_task(engine.demo_loop())  # fire and forget
    return {"status": "started", "using": engine.symbol}


@router.post("/demo/stop")
async def stop_demo(request: Request) -> Dict[str, Any]:
    request.app.state.demo_loop_running = False
    engine = _get_engine(request)
    engine.stop_demo()
    return {"status": "stopped"}


@router.get("/demo/status")
async def get_status(request: Request) -> Dict[str, Any]:
    running = _get_loop_state(request)
    engine = _get_engine(request)
    return {"running": running, "symbol": engine.symbol}

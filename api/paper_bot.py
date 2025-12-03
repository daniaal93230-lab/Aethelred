from fastapi import APIRouter, Request
from utils.logger import logger

"""
Paper Bot (DI-refactored)
---------------------------------------
This module now runs *entirely* through dependency injection.
No global state.
No @app.on_event.
No hidden background loops.

Your engine is created in lifespan.py → Services.paper_engine
and injected here via request.app.state.services.

FUTURE REMINDER (for LLM + human):
----------------------------------
The long-term architecture will support:

• Unified PaperEngine / LiveEngine interface
• Order simulation layer (fees, slippage, latency)
• Futures engine with isolated margin tracking
• Replay mode via deterministic market-state stream
• DI-driven multi-engine orchestrator
• Asynchronous execution queue

This module intentionally stays minimal until the
Futures Engine Architecture is introduced.
"""

router = APIRouter(tags=["paper"])


def get_paper_engine(request: Request):
    """Dependency helper to fetch DI-injected paper engine."""
    try:
        return request.app.state.services.paper_engine
    except Exception:
        raise RuntimeError("Paper engine not registered in app.state.services")


@router.get("/paper/start")
def start_paper_bot(request: Request):
    """
    Starts the paper engine’s background loop via DI.
    """
    engine = get_paper_engine(request)
    logger.info("Starting DI-driven paper engine loop...")
    engine.start_background_loop()
    return {"status": "ok", "detail": "paper engine loop started"}


@router.get("/paper/status")
def paper_status(request: Request):
    """
    Returns engine status.
    """
    engine = get_paper_engine(request)
    return engine.status()


@router.get("/paper/positions")
def paper_positions(request: Request):
    """
    Returns open paper-trading positions.
    """
    engine = get_paper_engine(request)
    return engine.list_positions()


@router.get("/paper/trades")
def paper_trades(request: Request):
    """
    Returns executed paper trades.
    """
    engine = get_paper_engine(request)
    return engine.list_trades()


@router.post("/paper/step")
def paper_step(request: Request):
    """
    Runs a single step of the execution engine (mock/testing).
    """
    engine = get_paper_engine(request)

    try:
        result = engine.run_once(is_mock=True)
    except Exception as e:
        logger.exception("Paper engine step failed")
        return {"ok": False, "error": str(e)}

    return {"ok": True, "result": result}


@router.get("/paper/next_signal")
def next_signal(request: Request, symbol: str = "BTC/USDT"):
    """
    Return the next signal for the given symbol.

    Query param `test=1` preserves legacy SMA test semantics (raw string).
    Production routes through engine strategos when available.
    """
    engine = None
    try:
        engine = get_paper_engine(request)
    except Exception:
        # attempt to read from app.state.services.engine as fallback
        services = getattr(request.app.state, "services", None)
        engine = getattr(services, "engine", None) if services else None

    if engine is None:
        raise RuntimeError("Paper engine not registered")

    testing = request.query_params.get("test") == "1"

    exch = getattr(engine, "exchange", None) or getattr(engine, "_exch", None)
    if exch is None:
        raise RuntimeError("Exchange unavailable")

    try:
        ohlcv = exch.fetch_ohlcv(symbol)
    except Exception:
        ohlcv = []

    if testing:
        from core.trade_logic import simple_moving_average_strategy

        raw = simple_moving_average_strategy(ohlcv)
        return {"raw": raw}

    strategos = getattr(engine, "_strategos", None) or getattr(engine, "strategos", None)
    if strategos is None:
        # fallback to SMA
        from core.trade_logic import simple_moving_average_strategy

        raw = simple_moving_average_strategy(ohlcv)
        return {"raw": raw}

    typed = strategos.route(ohlcv)
    return {"side": typed.side.value.lower(), "strength": typed.strength, "ttl": typed.ttl}

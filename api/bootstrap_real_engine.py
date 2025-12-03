"""
Bootstrap the real engine and attach it to FastAPI for uvicorn --factory.
Usage:
    uvicorn api.bootstrap_real_engine:create_app --host 127.0.0.1 --port 8080
Env:
    LIVE=1                to prevent QA engine auto attach
    SAFE_FLATTEN_ON_START optional safety on startup
    SNAPSHOT_IDLE_SEC     optional idle snapshot loop interval (default 15)
"""

from __future__ import annotations

import importlib
import os
from typing import Dict
from fastapi import FastAPI

# Import the FastAPI app and engine building blocks
# IMPORTANT: never import api.main here (creates circular import)
from api.deps.engine import build_engine
from api.core.orchestrator import MultiEngineOrchestrator, EngineOrchestrator
from core.execution_engine import ExecutionEngine
from utils.logger import logger

# module-level app handle; created inside create_app()
_app = None

IDLE_SNAPSHOT_SEC = int(os.getenv("SNAPSHOT_IDLE_SEC", "15") or "15")


# The concrete orchestrator implementation is provided by
# `api.core.orchestrator.Orchestrator` and re-exported as
# `api.deps.orchestrator.EngineOrchestrator` (EngineOrchestrator imported above).


def create_app() -> FastAPI:
    """
    Production bootstrap for uvicorn --factory.
    Responsibilities:
        • Build DI-backed DB/Risk/Exchange/Engine
        • Attach to _app.state.services
        • Attach Orchestrator as app.state.engine
        • Leave startup/shutdown to lifespan.py
    """

    # ----------------------------------------------------
    # Create FastAPI application instance (CRITICAL FIX)
    # ----------------------------------------------------
    global _app
    _app = FastAPI()

    os.environ["LIVE"] = os.getenv("LIVE", "1")

    # ---------------------------
    # Build the service container
    # ---------------------------
    services = type("Services", (), {})()

    # DB is not required for paper mode — disable DB for now
    services.db = None

    # Risk Engine (canonical)
    try:
        import api.deps.risk as risk_mod

        # Access dynamically so mypy does not require the attribute to exist
        build_risk = getattr(risk_mod, "build_risk")
        services.risk = build_risk(services.db)
    except Exception:
        services.risk = None

    # Exchange (canonical)
    try:
        import api.deps.exchange as exch_mod

        build_exchange = getattr(exch_mod, "build_exchange")
        services.exchange = build_exchange(
            db=services.db,
            risk=services.risk,
        )
    except Exception:
        services.exchange = None

    # 3) Exchange
    exchange = services.exchange

    # ---------------------------------------------------------------------
    # Patch PaperExchange to provide working OHLCV during PAPER mode
    # ---------------------------------------------------------------------
    from api.deps.settings import Settings, get_settings

    # Prefer pre-attached settings if present AND correct type, else load canonical settings
    raw_settings = getattr(services, "settings", None)
    if isinstance(raw_settings, Settings):
        settings: Settings = raw_settings
    else:
        settings = get_settings()

    if getattr(settings, "PAPER", False):
        try:
            # Legacy Exchange includes a working OHLCV method — import via shim
            from exchange import Exchange as LiveCompat

            # no mypy-ignore needed
            live = LiveCompat()

            # Patch method directly
            from typing import Any

            def _patched_fetch_ohlcv(symbol: str) -> Any:
                # LiveCompat supports CCXT-style OHLCV output
                return live.fetch_ohlcv(symbol)

            if exchange is not None:
                exchange.fetch_ohlcv = _patched_fetch_ohlcv

        except Exception as e:
            print(f"[bootstrap] PaperExchange OHLCV patch failed: {e}")

    # ------------------------------------------------------------------
    # Build per-symbol engines + orchestrators (multi-symbol architecture)
    # ------------------------------------------------------------------

    exch_mod = importlib.import_module("exchange.paper")
    PaperExchange = getattr(exch_mod, "PaperExchange")

    # derive symbols: prefer settings.symbols if present, else env AET_SYMBOLS
    raw = os.getenv("AET_SYMBOLS")
    if raw:
        symbols = [s.strip() for s in raw.split(",") if s.strip()]
    else:
        symbols = [getattr(settings, "symbol", "BTCUSDT")]

    engines: Dict[str, ExecutionEngine] = {}
    orchs: Dict[str, EngineOrchestrator] = {}

    for sym in symbols:
        logger.info("bootstrap_building_engine", extra={"symbol": sym})

        exch = PaperExchange()
        eng = build_engine(exchange=exch, settings=settings, symbol=sym)
        engines[sym] = eng

        orch = EngineOrchestrator(eng, sym)
        orchs[sym] = orch

    multi = MultiEngineOrchestrator(orchs)

    # attach to application
    _app.state.symbols = symbols
    _app.state.engines = engines
    _app.state.orchestrators = orchs
    _app.state.multi_orch = multi

    # populate a simple services container with useful references
    try:
        services.engines = engines
        services.orchestrators = orchs
        services.multi_orch = multi
        services.exchange = exchange
        services.portfolio_state = multi.portfolio_snapshot
        import time

        services.start_ts = time.time()
    except Exception:
        # best-effort only
        pass

    from api.routes.runtime import router as runtime_router

    _app.include_router(runtime_router, prefix="")

    # Configure ops notifier from settings when available (best-effort)
    try:
        from ops.notifier import notifier as ops_notifier

        ops_notifier.telegram_token = getattr(settings, "telegram_token", None)
        ops_notifier.telegram_chat_id = getattr(settings, "telegram_chat_id", None)
        ops_notifier.slack_webhook = getattr(settings, "slack_webhook", None)
    except Exception:
        pass

    @_app.on_event("startup")
    async def _startup() -> None:
        logger.info("bootstrap_startup_multi")
        await multi.start_all()

    @_app.on_event("shutdown")
    async def _shutdown() -> None:
        logger.info("bootstrap_shutdown_multi")
        await multi.stop_all()

    # Attach DI container
    _app.state.services = services


def services_or_none():
    # during tests and import-time the main FastAPI app may not be available
    try:
        if _app is None:
            return None
        return _app.state.services
    except Exception:
        return None

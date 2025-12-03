# api/lifespan.py

"""
Aethelred Lifespan Manager
--------------------------
Batch 6A-2: EngineOrchestrator wired into startup/shutdown.

Centralized dependency initialization for the entire FastAPI application.

This module performs:
- DB connection & shutdown
- Exchange / PaperExchange initialization
- Strategy Engine initialization
- Any service singletons
- Dependency Injection hydration

This is the canonical place for startup/shutdown logic.
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator
import asyncio

from fastapi import FastAPI
from api.deps.orchestrator import EngineOrchestrator
from core.runtime_state import kill_is_on


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Unified startup/shutdown lifecycle.
    """

    # Services injected via DI (DB, risk, exchange, orchestrator, etc.)
    services = getattr(app.state, "services", None)
    orchestrator = None

    # Batch 6D — Kill-switch blocks orchestrator/engine startup
    if kill_is_on():
        # system in HARD kill: skip orchestrator startup completely
        orchestrator = None
    else:
        # EngineOrchestrator startup (Batch 6A-2)
        if services:
            orchestrator = getattr(services, "engine_orchestrator", None)
            if isinstance(orchestrator, EngineOrchestrator):
                # start() is synchronous — it schedules an internal async loop
                try:
                    orchestrator.start()
                except Exception:
                    # tolerate failures on orchestrator start
                    pass

    # Start Ops Watchdog (best-effort, non-blocking)
    try:
        from ops.watchdog import watchdog_loop

        # schedule as background task in the running loop
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(watchdog_loop())
        except Exception:
            # fallback: start task via ensure_future
            asyncio.ensure_future(watchdog_loop())
    except Exception:
        pass

    # Startup tasks (DB schema, etc.)
    if services:
        db = getattr(services, "db", None)
        if db:
            try:
                db.ensure_schema()
            except Exception:
                pass

    try:
        yield
    finally:
        # Shutdown orchestrator
        if isinstance(orchestrator, EngineOrchestrator):
            # orchestrator.shutdown() is async
            try:
                await orchestrator.shutdown()
            except Exception:
                pass

        # Shutdown DB
        if services:
            db = getattr(services, "db", None)
            if db:
                try:
                    db.close()
                except Exception:
                    pass

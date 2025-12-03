from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from fastapi import Request

from api.deps.settings import Settings, get_settings

from exchange import PaperExchange, Exchange
from core.execution_engine import ExecutionEngine


@runtime_checkable
class ExecutionEngineProto(Protocol):
    def run_once(self, *args: Any, **kwargs: Any) -> Any: ...
    def train(self, job: str | None, notes: str | None) -> Any: ...


#
# Removed lightweight EngineOrchestrator implementation.
# Project Aethelred now uses the production-grade orchestrator in:
#     api.core.orchestrator
# This avoids duplicate control surfaces and ensures MultiEngine orchestration.
#


def build_engine(
    *,
    settings: Settings | None = None,
    exchange: Any | None = None,
    db: Any | None = None,
    risk: Any | None = None,
    symbol: str | None = None,
) -> ExecutionEngine:
    """
    Build the trading engine and wrap it in an EngineOrchestrator.

    Accepts optional exchange / db instances (injected by lifespan) and
    is defensive about the ExecutionEngine constructor signature so we
    stay compatible with both the current and future engine shapes.
    """
    settings = settings or get_settings()
    exch = exchange if exchange is not None else (PaperExchange() if settings.PAPER else Exchange())

    # Construct engine with defensive fallbacks
    try:
        engine = ExecutionEngine()
        engine.exchange = exch
        if symbol:
            engine.symbol = symbol
    except Exception:
        # worst case: minimal engine
        engine = ExecutionEngine()

    return engine


def get_engine(request: Request) -> Any:
    """
    FastAPI dependency used by routes that need the engine.

    Returns the orchestrator instance attached in lifespan/bootstrap,
    which behaves like the engine but also exposes enqueue_* helpers.
    """
    # app.state is dynamically populated at runtime (lifespan/bootstrap).
    # In test/TestClient mode `app.state.engine` can be absent or untyped,
    # so treat the dependency as `Any` for flexibility.
    return request.app.state.engine

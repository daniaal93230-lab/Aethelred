"""
Aethelred — Unified Dependency Injection Container
--------------------------------------------------

This file defines the central Services container used by the entire API layer.

Why this exists:
----------------
FastAPI's recommended pattern for lifespan apps (post-2023) is to use a single
dependency container attached to `app.state`. This allows:

    • clean startup/shutdown orchestration
    • consistent dependency injection (DI)
    • hot-swappable engines (paper, live, sim, ML)
    • unified database, risk engine, and exchange adapters
    • predictable testability (tests override app.state.services)
    • future expansion for:
        – ML inference models
        – orchestrator
        – portfolio engine
        – news/sentiment module
        – multi-exchange routing
        – metrics + tracing
        – background workers

This architecture removes:
    • global state
    • implicit imports
    • brittle `app.state.<var>` objects all over the codebase
    • unsafe lifecycles

Every route receives dependencies by calling:

    services = request.app.state.services
    engine = services.engine
    db = services.db

This file is intentionally stable and should rarely change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Any

from api.deps.settings import Settings
from db.db_manager import DBManager
from exchange import Exchange, PaperExchange
from core.execution_engine import ExecutionEngine
from risk.engine import RiskEngine


@dataclass
class Services:
    """
    DI container for the entire Aethelred API.

    Each field is explicitly typed so mypy --strict can validate that the
    lifespan layer is wiring everything correctly.

    Fields intentionally allow Optional[...] during startup, but your lifespan
    will guarantee they are set before the application begins accepting traffic.
    """

    # Core configuration
    settings: Settings

    # Database connection manager
    db: Optional[DBManager] = None

    # Exchange adapters
    exchange: Optional[Exchange] = None
    paper_exchange: Optional[PaperExchange] = None

    # Engines
    engine: Optional[ExecutionEngine] = None
    paper_engine: Optional[ExecutionEngine] = None

    # Risk engine
    risk_engine: Optional[RiskEngine] = None

    # Future Aethelred modules (reserved)
    ml_model: Optional[Any] = None
    orchestrator: Optional[Any] = None
    portfolio_engine: Optional[Any] = None

    def validate(self) -> None:
        """
        Ensure that all required components are wired before use.
        Called automatically at the end of lifespan startup.
        """
        # Minimal required components
        if self.db is None:
            raise RuntimeError("Services.db not initialised")

        if self.exchange is None:
            raise RuntimeError("Services.exchange not initialised")

        if self.engine is None:
            raise RuntimeError("Services.engine not initialised")

        if self.risk_engine is None:
            raise RuntimeError("Services.risk_engine not initialised")


__all__ = ["Services"]

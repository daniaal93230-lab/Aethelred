"""
Unified Health Endpoint (Phase 5)
--------------------------------
Provides DI-backed health checks used by runtime, tests, and orchestration.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel
import time

from utils.logger import setup_logger, log_json


router = APIRouter(prefix="/health", tags=["health"])
logger = setup_logger(__name__)


class HealthReport(BaseModel):
    status: str
    uptime_seconds: float
    db_ok: bool
    engine_ok: bool
    risk_ok: bool


@router.get("/", response_model=HealthReport)
async def health_root(request: Request) -> HealthReport:
    """
    Fully DI-backed health endpoint.
    Checks:
      - DB dependency
      - Engine dependency
      - Risk dependency
    """
    services = request.app.state.services
    start_ts = getattr(request.app.state, "start_time", time.time())

    db_ok = hasattr(services, "db")
    engine_ok = hasattr(services, "engine")
    risk_ok = hasattr(services, "risk")

    log_json(
        logger,
        "info",
        "healthcheck",
        status="ok" if (db_ok and engine_ok and risk_ok) else "degraded",
    )

    return HealthReport(
        status="ok" if (db_ok and engine_ok and risk_ok) else "degraded",
        uptime_seconds=time.time() - start_ts,
        db_ok=db_ok,
        engine_ok=engine_ok,
        risk_ok=risk_ok,
    )

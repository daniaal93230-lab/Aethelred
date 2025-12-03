from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi import Request

from api.services.insight_dashboard_builder import InsightDashboardBuilder
from api.models.insight_dashboard import InsightDashboard


router = APIRouter(prefix="/insight", tags=["insight-dashboard"])


# ---------------------------------------------------------
# GET /insight/dashboard/{symbol}
# ---------------------------------------------------------
@router.get(
    "/dashboard/{symbol}",
    response_model=InsightDashboard,
    summary="Full Insight Dashboard Snapshot",
    description="Returns rolling performance, MAE/MFE tables, KPIs and recent trades for the given symbol.",
)
async def get_insight_dashboard(request: Request, symbol: str) -> InsightDashboard:
    """
    Build and return a full InsightDashboard snapshot for a symbol.

    Relies on:
      - app.state.services.insight_engines
      - app.state.services.multi_orch
      - app.state.services.telemetry_history

    The endpoint is read-only, safe, and does not modify any existing behavior.
    """
    services = getattr(request.app.state, "services", None)
    if services is None:
        raise HTTPException(status_code=503, detail="Services not initialized")

    insight_engines = getattr(services, "insight_engines", None)
    orchestrator = getattr(services, "multi_orch", None)
    history = getattr(services, "telemetry_history", None)

    if insight_engines is None:
        raise HTTPException(status_code=500, detail="Insight engines unavailable")

    if symbol not in insight_engines:
        raise HTTPException(status_code=404, detail=f"No insight engine for {symbol}")

    insight_engine = insight_engines[symbol]

    if orchestrator is None:
        raise HTTPException(status_code=500, detail="Orchestrator unavailable")

    if history is None:
        raise HTTPException(status_code=500, detail="Telemetry history unavailable")

    builder = InsightDashboardBuilder(
        insight_engine=insight_engine,
        orchestrator=orchestrator,
        history=history,
        symbol=symbol,
    )

    return builder.build()

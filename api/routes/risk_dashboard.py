from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException

from api.services.risk_dashboard_builder import RiskDashboardBuilder
from api.models.risk_dashboard import RiskDashboard


router = APIRouter(
    prefix="/risk",
    tags=["risk-dashboard"],
)


# ---------------------------------------------------------
# GET /risk/dashboard/{symbol}
# ---------------------------------------------------------
@router.get(
    "/dashboard/{symbol}",
    response_model=RiskDashboard,
    summary="Risk Dashboard Snapshot",
    description="Returns volatility, exposure, risk state and position info for the given symbol.",
)
async def get_risk_dashboard(request: Request, symbol: str) -> RiskDashboard:
    """
    Builds and returns a RiskDashboard snapshot using:
      - services.risk_engines[symbol]
      - services.multi_orch (orchestrator)
      - services.engines[symbol]

    This endpoint is read-only and safe. No side-effects.
    """
    services = getattr(request.app.state, "services", None)
    if services is None:
        raise HTTPException(status_code=503, detail="Services not initialized")

    risk_engines = getattr(services, "risk_engines", None)
    orchestrator = getattr(services, "multi_orch", None)
    engines = getattr(services, "engines", None)

    if risk_engines is None or symbol not in risk_engines:
        raise HTTPException(status_code=404, detail=f"No risk engine for {symbol}")

    if engines is None or symbol not in engines:
        raise HTTPException(status_code=404, detail=f"No execution engine for {symbol}")

    if orchestrator is None:
        raise HTTPException(status_code=500, detail="Orchestrator unavailable")

    risk_engine = risk_engines[symbol]
    engine = engines[symbol]

    builder = RiskDashboardBuilder(
        symbol=symbol,
        risk_engine=risk_engine,
        orchestrator=orchestrator,
        engine=engine,
    )

    return builder.build()

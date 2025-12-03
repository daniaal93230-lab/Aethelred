from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException

from api.models.multisymbol_dashboard import MultiSymbolDashboard
from api.services.multisymbol_dashboard_builder import MultiSymbolDashboardBuilder


router = APIRouter(
    prefix="/dashboard",
    tags=["multi-symbol-dashboard"],
)


# ---------------------------------------------------------
# GET /dashboard/multi
# Unified multi-symbol dashboard snapshot
# ---------------------------------------------------------
@router.get(
    "/multi",
    response_model=MultiSymbolDashboard,
    summary="Unified Multi-Symbol Dashboard",
    description=(
        "Returns compact insight, risk, and ops summaries for all symbols along with portfolio-wide metrics and alerts."
    ),
)
async def get_multi_symbol_dashboard(request: Request) -> MultiSymbolDashboard:
    """
    Builds the unified multi-symbol dashboard using:
      - insight_engines
      - risk_engines
      - engines
      - multi_orch (for exposure + health)

    Purely read-only. Fully safe.
    """
    services = getattr(request.app.state, "services", None)
    if services is None:
        raise HTTPException(status_code=503, detail="Services not initialized")

    builder = MultiSymbolDashboardBuilder(services)
    return builder.build()

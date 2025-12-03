from __future__ import annotations

from fastapi import APIRouter, Depends
from typing import Any, List

from api.deps.orchestrator_v2 import get_orchestrator


router = APIRouter(prefix="/telemetry/history", tags=["telemetry-history"])


@router.get("/symbol/{symbol}")
def history_symbol(symbol: str, orchestrator=Depends(get_orchestrator)) -> List[Any]:
    """Return rolling history for a symbol."""
    return orchestrator.history.get_symbol_history(symbol)


@router.get("/portfolio")
def history_portfolio(orchestrator=Depends(get_orchestrator)) -> List[Any]:
    """Return portfolio-level rolling history."""
    return orchestrator.history.get_portfolio_history()

from __future__ import annotations

from fastapi import APIRouter, Depends
from typing import Any, Dict

from api.deps.orchestrator_v2 import get_orchestrator


router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.get("/portfolio")
def get_portfolio(orchestrator=Depends(get_orchestrator)) -> Dict[str, Any]:
    """Return aggregated portfolio telemetry snapshot."""
    snap = orchestrator.snapshot()
    return snap.get("portfolio", {})


@router.get("/symbols")
def get_all_symbols(orchestrator=Depends(get_orchestrator)) -> Dict[str, Any]:
    """Return all symbol snapshots."""
    snap = orchestrator.snapshot()
    return snap.get("symbols", {})


@router.get("/symbol/{symbol}")
def get_symbol(symbol: str, orchestrator=Depends(get_orchestrator)) -> Dict[str, Any]:
    """Return telemetry for a single symbol."""
    snap = orchestrator.snapshot()
    return snap.get("symbols", {}).get(symbol, {})


@router.get("/raw")
def get_raw(orchestrator=Depends(get_orchestrator)) -> Dict[str, Any]:
    """Return raw orchestrator snapshot (symbols + portfolio)."""
    return orchestrator.snapshot()

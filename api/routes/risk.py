from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException, Request
from api.bootstrap_real_engine import services_or_none
from decimal import Decimal

router = APIRouter()


@router.get("/risk")
async def risk_root():
    """
    Phase 6.D-1 — Risk V3 telemetry endpoint.
    Non intrusive: returns empty values if V3 disabled.
    """
    sv = services_or_none()
    if sv is None:
        return {"risk_v3": None, "status": "no-services"}

    engines = getattr(sv, "engines", None)
    if not engines:
        return {"risk_v3": None, "status": "no-engines"}

    out = {}

    for sym, eng in engines.items():
        try:
            r3 = getattr(eng, "risk_v3", None)
            if r3 is None:
                out[sym] = {"enabled": False, "snapshot": None}
                continue

            snap = r3.telemetry_snapshot()

            # Ensure Decimal values serialize OK
            def _clean(v):
                if isinstance(v, Decimal):
                    return float(v)
                if isinstance(v, dict):
                    return {k: _clean(x) for k, x in v.items()}
                return v

            out[sym] = {
                "enabled": getattr(eng, "risk_v3_enabled", False),
                "snapshot": _clean(snap),
            }

        except Exception:
            out[sym] = {"enabled": False, "snapshot": None, "error": True}

    return {"risk_v3": out, "status": "ok"}


# --------------------------------------------------------------------
# DI-based RiskEngine access
#
# All risk calls now use:
#   request.app.state.services.risk_engine
#
# If DI is missing (should never happen in lifespan-based boot),
# we throw a 500 with a clear message.
# --------------------------------------------------------------------


def _get_risk_engine(request: Request) -> Any:
    services = getattr(request.app.state, "services", None)
    engine = getattr(services, "risk_engine", None) if services else None
    if engine is None:
        raise HTTPException(status_code=500, detail="Risk engine not available")
    return engine


@router.get("/profile")
async def get_risk_profile(request: Request) -> Any:
    engine = _get_risk_engine(request)
    try:
        return engine.get_profile()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/limits")
async def get_limits(request: Request) -> Any:
    engine = _get_risk_engine(request)
    try:
        return engine.get_limits()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/metrics")
async def get_metrics(request: Request) -> Any:
    engine = _get_risk_engine(request)
    try:
        return engine.get_metrics()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

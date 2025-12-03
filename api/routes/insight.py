from fastapi import APIRouter
from api.bootstrap_real_engine import services_or_none
from decimal import Decimal
from typing import Any, Dict

router = APIRouter()


def _clean(v: Any):
    """Convert Decimal → float recursively."""
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_clean(x) for x in v]
    return v


@router.get("/insight/daily")
async def insight_daily() -> Dict[str, Any]:
    """
    Phase 6.E-5
    Returns a JSON version of the daily KPI snapshot.
    Does NOT write any CSV.
    """
    sv = services_or_none()
    if sv is None:
        return {"status": "no-services", "insight": None}

    engines = getattr(sv, "engines", None)
    if not engines:
        return {"status": "no-engines", "insight": None}

    out: Dict[str, Any] = {}
    for sym, eng in engines.items():
        if not getattr(eng, "insight_enabled", False):
            out[sym] = {"enabled": False, "snapshot": None}
            continue

        ins = getattr(eng, "insight", None)
        if not ins:
            out[sym] = {"enabled": False, "snapshot": None}
            continue

        # Full insight snapshot (strategies, regimes, rolling metrics)
        snap = ins.snapshot()
        out[sym] = {
            "enabled": True,
            "snapshot": _clean(snap),
        }

    return {"status": "ok", "insight": out}


@router.get("/insight/strategy/{name}")
async def insight_strategy(name: str) -> Dict[str, Any]:
    """
    Phase 6.E-5
    Returns MAE/MFE aggregates for a specific strategy.
    """
    sv = services_or_none()
    if sv is None:
        return {"status": "no-services", "strategy": None}

    engines = getattr(sv, "engines", None)
    if not engines:
        return {"status": "no-engines", "strategy": None}

    out: Dict[str, Any] = {}
    for sym, eng in engines.items():
        if not getattr(eng, "insight_enabled", False):
            out[sym] = {"enabled": False, "strategy": None}
            continue

        ins = getattr(eng, "insight", None)
        if not ins:
            out[sym] = {"enabled": False, "strategy": None}
            continue

        stats = ins.strategy_stats.get(name)
        if not stats:
            out[sym] = {"enabled": True, "strategy": None}
            continue

        cleaned = {
            "count": float(stats.get("count", 0)),
            "avg_mae": float(stats["sum_mae"] / stats["count"]) if stats.get("count") else 0,
            "avg_mfe": float(stats["sum_mfe"] / stats["count"]) if stats.get("count") else 0,
        }

        out[sym] = {"enabled": True, "strategy": cleaned}

    return {"status": "ok", "strategy": out}

import time
from fastapi import APIRouter
from api.bootstrap_real_engine import services_or_none

router = APIRouter()


@router.get("/health")
async def health_root():
    sv = services_or_none()

    api_info = {
        "status": "ok",
        "uptime_sec": time.time() - sv.start_ts if sv and hasattr(sv, "start_ts") else None,
        "version": "5.D",
    }

    if sv is None:
        return {"api": api_info, "engines": None, "orchestrators": None}

    # orchestrator-level
    orch = getattr(sv, "multi_orch", None)
    orch_data = orch.status() if orch is not None else None

    # per-symbol engine health
    engine_info = {}
    for sym, eng in getattr(sv, "engines", {}).items():
        try:
            last_cycle_ms = None
            last_cycle_ts = None
            kill_flags = None
            if orch is not None:
                last_cycle_ms = (
                    getattr(orch, "_last_cycle_ms", {}).get(sym) if hasattr(orch, "_last_cycle_ms") else None
                )
                last_cycle_ts = getattr(orch, "last_cycle_ts", {}).get(sym) if hasattr(orch, "last_cycle_ts") else None
                kill_flags = getattr(orch, "kill_flags", {}).get(sym) if hasattr(orch, "kill_flags") else None

            state = getattr(eng, "state", None)

            engine_info[sym] = {
                "last_cycle_ms": last_cycle_ms,
                "last_cycle_ts": last_cycle_ts,
                "regime": getattr(state, "last_regime", None) if state else getattr(eng, "last_regime", None),
                "signal": getattr(state, "last_signal", None) if state else getattr(eng, "last_signal", None),
                "kill_flags": kill_flags,
                "consecutive_losses": getattr(state, "consecutive_losses", None)
                if state
                else getattr(eng, "_loss_streak", None),
                "position_size": float(getattr(state, "position_size", 0)) if state else None,
                "volatility_anomaly": getattr(state, "volatility_anomaly", None) if state else None,
                "ml_veto_spikes": getattr(state, "ml_veto_spikes", None) if state else None,
            }
        except Exception:
            engine_info[sym] = {"error": "engine health read failed"}

    # exchange probe
    exch = getattr(sv, "exchange", None)
    exch_health = {}
    try:
        if exch is not None and hasattr(exch, "health_probe"):
            t0 = time.perf_counter()
            await exch.health_probe()
            dt = (time.perf_counter() - t0) * 1000
            exch_health = {"status": "ok", "latency_ms": dt}
        else:
            exch_health = {"status": "na"}
    except Exception:
        exch_health = {"status": "error"}

    # risk summary
    risk = {
        "portfolio_drawdown": getattr(getattr(sv, "portfolio_state", {}), "get", lambda k, d=None: d)(
            "drawdown_pct", None
        ),
        "risk_off": getattr(orch, "global_risk_off", None) if orch is not None else None,
        "hard_drawdown": getattr(orch, "_hard_dd_alerted", None) if orch is not None else None,
        # ----------------------------------------------------
        # Phase 6.D-2 — include RiskEngineV3 quick summary
        # ----------------------------------------------------
        "risk_v3": {},
    }

    try:
        for sym, eng in getattr(sv, "engines", {}).items():
            r3 = getattr(eng, "risk_v3", None)
            if not r3:
                risk["risk_v3"][sym] = {"enabled": False}
                continue

            snap = r3.telemetry_snapshot()
            risk["risk_v3"][sym] = {
                "enabled": getattr(eng, "risk_v3_enabled", False),
                "volatility": float(snap.get("volatility", 0)),
                "portfolio_vol": float(snap.get("portfolio_vol", 0)),
                "scaling_factor": float(snap.get("scaling_factor", 1)),
                "total_exposure": float(snap.get("total_exposure", 0)),
            }
    except Exception:
        pass

    return {
        "api": api_info,
        "orchestrators": orch_data,
        "engines": engine_info,
        "exchange": exch_health,
        "risk": risk,
        "watchdog": {
            "running": True if sv is not None else False,
            "interval_sec": 5.0,
            "slow_factor": 2.0,
        },
    }

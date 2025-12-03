from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, cast

from fastapi import APIRouter, HTTPException, Request, Response
import os
from utils.logger import logger
from core.runtime_state import RUNTIME_DIR
from core.runtime_state import kill_is_on, kill_on, kill_off
from core.runtime_state import read_events
from core.runtime_state import prometheus_format
from fastapi.responses import JSONResponse

router = APIRouter()


@router.post("/start")
async def start_all(request: Request) -> Dict[str, Any]:
    multi = getattr(request.app.state, "multi_orch", None)
    if multi is None:
        raise HTTPException(status_code=503, detail="multi orchestrator not configured")
    logger.info("runtime_start_request")
    await multi.start_all()
    return {"status": "started", "symbols": multi.symbols}


@router.post("/stop")
async def stop_all(request: Request) -> Dict[str, Any]:
    multi = getattr(request.app.state, "multi_orch", None)
    if multi is None:
        raise HTTPException(status_code=503, detail="multi orchestrator not configured")
    await multi.stop_all()
    return {"status": "stopped", "symbols": multi.symbols}


@router.get("/status")
async def status(request: Request) -> Dict[str, Any]:
    multi = getattr(request.app.state, "multi_orch", None)
    if multi:
        # multi.status() is dynamically typed; cast to the declared return type
        return cast(Dict[str, Any], multi.status())
    return {}


def _qa_like() -> bool:
    return os.getenv("QA_DEV_ENGINE") == "1" or os.getenv("MODE") == "paper"


def _first_non_empty_list(*candidates: Any) -> List[Any] | None:
    for c in candidates:
        if isinstance(c, list) and len(c) > 0:
            return c
    return None


def _dict_list(d: Any, key: str) -> List[Any] | None:
    return d.get(key) if isinstance(d, dict) and isinstance(d.get(key), list) else None


def _safe_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


def _build_snapshot(engine: Any) -> Dict[str, Any]:
    """
    Build a best-effort runtime snapshot from the in-proc engine.
    This avoids relying on any filesystem path.
    Expected-by-Visor keys:
      - heartbeat_ts (ISO8601)
      - equity: list[{ts, equity}]  (optional if not available)
      - positions: list[{symbol, side, qty, entry, mark, unrealized_pct, selector.strategy_name?}]
      - realized_pnl_today_usd (optional)
      - trade_count_today (optional)
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    out: Dict[str, Any] = {
        "heartbeat_ts": now_iso,
        "equity": [],
        "positions": [],
    }

    # KPIs if exposed on the engine
    for k in ("realized_pnl_today_usd", "trade_count_today"):
        val = getattr(engine, k, None)
        out[k] = val

    # If engine exposes account_snapshot(), prefer it as the canonical source
    # for equity and positions (QADevEngine and orchestrators implement this).
    try:
        if hasattr(engine, "account_snapshot") and callable(getattr(engine, "account_snapshot")):
            acct = engine.account_snapshot()
            if isinstance(acct, dict):
                if not out.get("equity"):
                    if isinstance(acct.get("equity"), list):
                        out["equity"] = [
                            {"ts": r.get("ts"), "equity": _safe_float(r.get("equity"))}
                            for r in acct.get("equity", [])
                            if isinstance(r, dict) and r.get("ts") is not None
                        ]
                    elif acct.get("equity_now") is not None:
                        out["equity"] = [{"ts": acct.get("ts"), "equity": _safe_float(acct.get("equity_now"))}]
                if not out.get("positions") and isinstance(acct.get("positions"), list):
                    acct_rows: List[Dict[str, Any]] = []
                    for p in acct.get("positions", []):
                        if not isinstance(p, dict):
                            continue
                        acct_rows.append(
                            {
                                "symbol": p.get("symbol"),
                                "side": p.get("side"),
                                "qty": _safe_float(p.get("qty")),
                                "entry": _safe_float(p.get("entry")),
                                "mark": _safe_float(p.get("mark")),
                                "unrealized_pct": _safe_float(p.get("mtm_pnl_pct")),
                                "selector": {"strategy_name": p.get("strategy_name")},
                            }
                        )
                    if acct_rows:
                        out["positions"] = acct_rows
    except Exception:
        pass

    # If a runtime snapshot file exists (written by the engine helper), prefer
    # that data when in-proc attributes are missing. This is a robust fallback
    # for engines that persist their runtime to disk but don't mirror it on
    # object attributes.
    try:
        snap_path = RUNTIME_DIR / "account_runtime.json"
        if snap_path.exists():
            raw = json.loads(snap_path.read_text(encoding="utf-8"))
            # file may expose 'equity' as list or 'equity_now' scalar
            if not out.get("equity"):
                if isinstance(raw.get("equity"), list):
                    out["equity"] = [
                        {"ts": r.get("ts"), "equity": _safe_float(r.get("equity"))}
                        for r in raw.get("equity", [])
                        if isinstance(r, dict) and r.get("ts") is not None
                    ]
                elif raw.get("equity_now") is not None:
                    out["equity"] = [{"ts": raw.get("ts"), "equity": _safe_float(raw.get("equity_now"))}]
            if not out.get("positions") and isinstance(raw.get("positions"), list):
                snap_rows: List[Dict[str, Any]] = []
                for p in raw.get("positions", []):
                    if not isinstance(p, dict):
                        continue
                    snap_rows.append(
                        {
                            "symbol": p.get("symbol"),
                            "side": p.get("side"),
                            "qty": _safe_float(p.get("qty")),
                            "entry": _safe_float(p.get("entry")),
                            "mark": _safe_float(p.get("mark")),
                            "unrealized_pct": _safe_float(p.get("mtm_pnl_pct")),
                            "selector": {"strategy_name": p.get("strategy_name")},
                        }
                    )
                if snap_rows:
                    out["positions"] = snap_rows
    except Exception:
        # don't let snapshot read errors break the endpoint
        pass

    # equity history if engine keeps it
    eq_hist = getattr(engine, "equity_history", None) or getattr(engine, "equity_series", None)
    # allow a dict with 'equity' key too
    if not isinstance(eq_hist, list):
        eq_hist = getattr(engine, "runtime_snapshot", None)
        if isinstance(eq_hist, dict) and isinstance(eq_hist.get("equity"), list):
            eq_hist = eq_hist["equity"]

    # fallback: engine.state or engine.snapshot may contain same data
    if not eq_hist:
        alt = getattr(engine, "state", None) or getattr(engine, "snapshot", None)
        if isinstance(alt, dict):
            maybe_eq = alt.get("equity") or alt.get("equity_series")
            if isinstance(maybe_eq, list):
                eq_hist = maybe_eq
    if isinstance(eq_hist, list):
        eq_rows_hist: List[Dict[str, Any]] = []
        for row in eq_hist:
            ts = row.get("ts") if isinstance(row, dict) else None
            eq = row.get("equity") if isinstance(row, dict) else None
            if ts is None or eq is None:
                continue
            eq_rows_hist.append({"ts": ts, "equity": _safe_float(eq)})
        out["equity"] = eq_rows_hist

    # open positions
    pos_list = getattr(engine, "positions", None) or getattr(engine, "open_positions", None)
    if pos_list is None:
        snap = getattr(engine, "runtime_snapshot", None)
        if isinstance(snap, dict) and isinstance(snap.get("positions"), list):
            pos_list = snap["positions"]

    # additional fallback: check engine.state or engine.snapshot
    if (not pos_list) and hasattr(engine, "state"):
        alt = getattr(engine, "state", None)
        if isinstance(alt, dict) and isinstance(alt.get("positions"), list):
            pos_list = alt["positions"]

    if (not pos_list) and hasattr(engine, "snapshot"):
        alt = getattr(engine, "snapshot", None)
        if isinstance(alt, dict) and isinstance(alt.get("positions"), list):
            pos_list = alt["positions"]
    if isinstance(pos_list, list):
        pos_rows: List[Dict[str, Any]] = []
        for p in pos_list:
            # Support both dict-like and object-like positions
            get = p.get if hasattr(p, "get") else lambda k, d=None: getattr(p, k, d)
            sel = get("selector", {}) if hasattr(p, "get") else getattr(p, "selector", {}) or {}
            pos_rows.append(
                {
                    "symbol": get("symbol", ""),
                    "side": get("side", ""),
                    "qty": _safe_float(get("qty", None)),
                    "entry": _safe_float(get("entry", None)),
                    "mark": _safe_float(get("mark", None)),
                    "unrealized_pct": _safe_float(get("unrealized_pct", None)),
                    "selector": {
                        "strategy_name": getattr(sel, "strategy_name", None)
                        if not isinstance(sel, dict)
                        else sel.get("strategy_name"),
                    },
                }
            )
        out["positions"] = pos_rows

    # Additional broad scan: if we still have empty equity or positions, try to
    # inspect other engine attributes for dict/list shapes that look like the
    # runtime_snapshot. This helps when the engine stores data under
    # non-canonical names (e.g. engine._state, engine._runtime, nested dicts).
    if not out.get("equity"):
        for attr in dir(engine):
            if attr.startswith("_"):
                continue
            try:
                val = getattr(engine, attr)
            except Exception:
                continue
            # dicts with 'equity' or 'equity_series' keys
            if isinstance(val, dict):
                maybe_eq = val.get("equity") or val.get("equity_series")
                if isinstance(maybe_eq, list):
                    eq_rows_attr: List[Dict[str, Any]] = []
                    for row in maybe_eq:
                        ts = row.get("ts") if isinstance(row, dict) else None
                        eq = row.get("equity") if isinstance(row, dict) else None
                        if ts is None or eq is None:
                            continue
                        eq_rows_attr.append({"ts": ts, "equity": _safe_float(eq)})
                    if eq_rows_attr:
                        out["equity"] = eq_rows_attr
                        break
            # lists of dicts that look like equity points
            if isinstance(val, list) and val:
                first = val[0]
                if isinstance(first, dict) and "ts" in first and ("equity" in first or "value" in first):
                    eq_rows_list: List[Dict[str, Any]] = []
                    for row in val:
                        if not isinstance(row, dict):
                            continue
                        ts = row.get("ts")
                        eq = row.get("equity") or row.get("value")
                        if ts is None or eq is None:
                            continue
                        eq_rows_list.append({"ts": ts, "equity": _safe_float(eq)})
                    if eq_rows_list:
                        out["equity"] = eq_rows_list
                        break

    if not out.get("positions"):
        for attr in dir(engine):
            if attr.startswith("_"):
                continue
            try:
                val = getattr(engine, attr)
            except Exception:
                continue
            # dicts with 'positions' key
            if isinstance(val, dict) and isinstance(val.get("positions"), list):
                pos_list = val.get("positions")
            # direct lists that look like positions
            if isinstance(val, list) and val:
                first = val[0]
                if isinstance(first, dict) and ("symbol" in first or "qty" in first):
                    pos_list = val
            if isinstance(pos_list, list):
                pos_rows2: List[Dict[str, Any]] = []
                for p in pos_list:
                    get = p.get if hasattr(p, "get") else lambda k, d=None: getattr(p, k, d)
                    sel = get("selector", {}) if hasattr(p, "get") else getattr(p, "selector", {}) or {}
                    pos_rows2.append(
                        {
                            "symbol": get("symbol", ""),
                            "side": get("side", ""),
                            "qty": _safe_float(get("qty", None)),
                            "entry": _safe_float(get("entry", None)),
                            "mark": _safe_float(get("mark", None)),
                            "unrealized_pct": _safe_float(get("unrealized_pct", None)),
                            "selector": {
                                "strategy_name": getattr(sel, "strategy_name", None)
                                if not isinstance(sel, dict)
                                else sel.get("strategy_name"),
                            },
                        }
                    )
                if pos_rows2:
                    out["positions"] = pos_rows2
                    break

    return out


# ------------------------------------------------------------
# Batch 6D — Kill Switch Endpoints
# ------------------------------------------------------------


@router.get("/runtime/kill")
def get_kill_state() -> Dict[str, Any]:
    """Return kill switch state."""
    return {"kill": kill_is_on()}


@router.post("/runtime/kill")
def activate_kill() -> Dict[str, Any]:
    """Activate global kill-switch."""
    kill_on()
    return {"kill": True}


@router.post("/runtime/kill/off")
def deactivate_kill() -> Dict[str, Any]:
    """Deactivate global kill-switch."""
    kill_off()
    return {"kill": False}


@router.get("/runtime/account_runtime.json")
def account_runtime(request: Request, symbol: str | None = None) -> Dict[str, Any]:
    app = request.app
    engines = getattr(app.state, "engine", None)

    # Multi-engine case (Batch 6E)
    if isinstance(engines, dict):
        if not symbol:
            raise HTTPException(status_code=400, detail="symbol is required")
        engine = engines.get(symbol)
        if engine is None:
            raise HTTPException(status_code=404, detail=f"symbol {symbol} not found")
    else:
        engine = engines

    if engine is None:
        raise HTTPException(status_code=503, detail="engine not attached")

    # equity history with generous fallbacks
    equity_series: List[Any] = []
    eq_candidates: List[Any] = []
    eq_candidates.append(getattr(engine, "equity_history", None))
    eq_candidates.append(getattr(engine, "equity_series", None))
    eq_candidates.append(_dict_list(getattr(engine, "runtime_snapshot", None), "equity"))
    eq_candidates.append(_dict_list(getattr(engine, "state", None), "equity"))
    eq_candidates.append(_dict_list(getattr(engine, "snapshot", None), "equity"))
    # allow a callable snapshot accessor if present
    getter = getattr(engine, "account_snapshot", None) or getattr(engine, "get_runtime", None)
    try:
        maybe = getter() if callable(getter) else None
        # If the callable snapshot exposes a scalar 'equity_now' (common for QA engines), use it preferentially
        if isinstance(maybe, dict) and maybe.get("equity_now") is not None:
            ts_val = maybe.get("ts")
            if ts_val is None:
                from datetime import datetime

                ts_val = int(datetime.now(timezone.utc).timestamp())
            equity_series = [{"ts": ts_val, "equity": _safe_float(maybe.get("equity_now"))}]
        else:
            eq_candidates.append(_dict_list(maybe, "equity"))
    except Exception:
        pass
    eq_first = _first_non_empty_list(*eq_candidates)
    if isinstance(eq_first, list):
        equity_series = eq_first

    # If the callable snapshot exposes a scalar 'equity_now' (QA engines often do), prefer that
    if not equity_series:
        try:
            maybe2 = getter() if callable(getter) else None
            if isinstance(maybe2, dict) and maybe2.get("equity_now") is not None:
                # prefer explicit ts if available, else use now()
                ts_val = maybe2.get("ts")
                if ts_val is None:
                    from datetime import datetime

                    ts_val = int(datetime.now(timezone.utc).timestamp())
                equity_series = [{"ts": ts_val, "equity": _safe_float(maybe2.get("equity_now"))}]
        except Exception:
            pass

    # open positions with generous fallbacks
    positions: List[Dict[str, Any]] = []
    pos_candidates: List[Any] = []
    pos_candidates.append(getattr(engine, "positions", None))
    pos_candidates.append(getattr(engine, "open_positions", None))
    pos_candidates.append(_dict_list(getattr(engine, "runtime_snapshot", None), "positions"))
    pos_candidates.append(_dict_list(getattr(engine, "state", None), "positions"))
    pos_candidates.append(_dict_list(getattr(engine, "snapshot", None), "positions"))
    try:
        maybe = getter() if callable(getter) else None
        pos_candidates.append(_dict_list(maybe, "positions"))
    except Exception:
        pass
    pos_first = _first_non_empty_list(*pos_candidates)
    if isinstance(pos_first, list):
        positions = pos_first

    # small KPIs for Visor
    realized_pnl = getattr(engine, "realized_pnl_today_usd", None)
    trade_count = getattr(engine, "trade_count_today", None)
    # try dict holders too
    if realized_pnl is None:
        for holder in (
            getattr(engine, "runtime_snapshot", None),
            getattr(engine, "state", None),
            getattr(engine, "snapshot", None),
        ):
            if isinstance(holder, dict) and "realized_pnl_today_usd" in holder:
                realized_pnl = holder["realized_pnl_today_usd"]
                break
    if trade_count is None:
        for holder in (
            getattr(engine, "runtime_snapshot", None),
            getattr(engine, "state", None),
            getattr(engine, "snapshot", None),
        ):
            if isinstance(holder, dict) and "trade_count_today" in holder:
                trade_count = holder["trade_count_today"]
                break

    # Last-resort: check persisted runtime file under the configured RUNTIME_DIR
    try:
        snap_path = RUNTIME_DIR / "account_runtime.json"
        disk = None
        if snap_path.exists():
            try:
                disk = json.loads(snap_path.read_text(encoding="utf-8"))
            except Exception:
                disk = None

        # If disk snapshot exists, compare timestamps and prefer disk if it's newer
        if disk:
            # parse disk ts (written_at_iso preferred, fallback to ts/heartbeat_ts)
            disk_ts = None
            for k in ("written_at_iso", "heartbeat_ts", "ts"):
                v = disk.get(k)
                if isinstance(v, str):
                    try:
                        disk_ts = datetime.fromisoformat(v)
                        break
                    except Exception:
                        try:
                            # maybe epoch seconds
                            disk_ts = datetime.fromtimestamp(float(v), timezone.utc)
                            break
                        except Exception:
                            disk_ts = None

            # derive in-proc timestamp if available
            inproc_ts = None
            try:
                # prefer getter-provided ts on the callable snapshot
                getter = getattr(engine, "account_snapshot", None) or getattr(engine, "get_runtime", None)
                maybe = getter() if callable(getter) else None
                if isinstance(maybe, dict) and maybe.get("ts") is not None:
                    ts_val = maybe.get("ts")
                    try:
                        if isinstance(ts_val, (int, float)):
                            inproc_ts = datetime.fromtimestamp(float(ts_val), timezone.utc)
                        else:
                            inproc_ts = datetime.fromisoformat(str(ts_val))
                    except Exception:
                        inproc_ts = None
            except Exception:
                inproc_ts = None

            # Choose disk when inproc is empty OR disk_ts is newer than inproc_ts
            prefer_disk = False
            if not equity_series or not positions:
                prefer_disk = True
            elif disk_ts and inproc_ts and disk_ts > inproc_ts:
                prefer_disk = True

            if prefer_disk:
                if not equity_series:
                    if isinstance(disk.get("equity"), list):
                        equity_series = disk.get("equity")
                    elif disk.get("equity_now") is not None:
                        equity_series = [{"ts": disk.get("ts"), "equity": _safe_float(disk.get("equity_now"))}]
                if not positions and isinstance(disk.get("positions"), list):
                    positions = disk.get("positions")
    except Exception:
        # don't let snapshot read errors break the endpoint
        pass

    return {
        "heartbeat_ts": datetime.now(timezone.utc).isoformat(),
        "equity": equity_series or [],
        "positions": positions or [],
        "realized_pnl_today_usd": realized_pnl,
        "trade_count_today": trade_count,
    }


@router.get("/runtime/inspect_engine.json")
def runtime_inspect_engine(request: Request) -> JSONResponse:
    """Diagnostic inspector (QA/private). The route is always registered but
    will return 404 if QA flags are not present in the process environment.
    This avoids race conditions where envs at import time may differ from
    those seen at runtime while keeping the endpoint hidden in non-QA runs.
    """
    # runtime check for QA-like mode
    if not _qa_like():
        raise HTTPException(status_code=404, detail="Not Found")

    app = request.app
    engine = getattr(app.state, "engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="engine not attached")
    keys = [
        "account_snapshot",
        "equity_history",
        "equity_series",
        "positions",
        "open_positions",
        "runtime_snapshot",
        "state",
        "snapshot",
        "realized_pnl_today_usd",
        "trade_count_today",
    ]
    out: Dict[str, Any] = {"attrs": []}
    for k in keys:
        try:
            v = getattr(engine, k, None)
            out["attrs"].append(
                {"name": k, "type": ("callable" if callable(v) else type(v).__name__), "callable": callable(v)}
            )
        except Exception:
            out["attrs"].append({"name": k, "type": "error", "callable": False})
    return JSONResponse(out)


# New: tiny env inspector to prove what the running uvicorn actually sees.
# This helps verify that the process answering requests has the QA flags we
# expect without exposing the full environment in production.
@router.get("/runtime/inspect_env.json")
def runtime_inspect_env() -> JSONResponse:
    keys = ["MODE", "QA_DEV_ENGINE", "SAFE_FLATTEN_ON_START"]
    env = {k: os.getenv(k) for k in keys}
    return JSONResponse({"env": env, "qa_like": _qa_like()})


# ------------------------------------------------------------
# Batch 7 — Telemetry endpoint
# ------------------------------------------------------------
@router.get("/telemetry")
def runtime_telemetry(request: Request) -> Dict[str, Any]:
    """
    Unified telemetry for Visor dashboards.
    Includes:
      - recent events
      - orchestrator metrics
      - per-symbol engine status
      - kill status
    """
    services = getattr(request.app.state, "services", None)
    orch = getattr(services, "engine_orchestrator", None) if services else None

    if orch is None:
        return {"kill": kill_is_on(), "events": read_events(), "orchestrator": None}

    return {
        "kill": kill_is_on(),
        "events": read_events(),
        "orchestrator": orch.metrics if hasattr(orch, "metrics") else {},
        "symbols": {
            sym: {
                "last_signal": getattr(engine, "last_signal", None),
                "last_regime": getattr(engine, "last_regime", None),
                # Risk v2 telemetry (Phase 3.G)
                "risk_v2_enabled": getattr(engine, "risk_v2_enabled", False),
                "drawdown": float(getattr(engine, "current_drawdown", 0)),
                "max_equity_seen": float(getattr(engine, "max_equity_seen", 0)),
                "loss_streak": int(getattr(engine, "_loss_streak", 0)),
                "risk_off": bool(getattr(engine, "risk_off", False)),
                "global_risk_off": bool(getattr(engine, "global_risk_off", False)),
                "per_symbol_limit": float(getattr(engine, "per_symbol_exposure_limit", 0)),
                "portfolio_limit": float(getattr(engine, "global_portfolio_limit", 0)),
            }
            for sym, engine in getattr(orch, "engines", {}).items()
        },
    }


@router.post("/runtime/pause")
def runtime_pause(request: Request) -> Dict[str, Any]:
    """Pause orchestrator processing (skip per-symbol cycles)."""
    services = getattr(request.app.state, "services", None)
    orch = getattr(services, "engine_orchestrator", None) if services else None
    if orch is None:
        raise HTTPException(status_code=503, detail="orchestrator not available")
    try:
        orch.is_paused = True
    except Exception:
        raise HTTPException(status_code=500, detail="failed to pause orchestrator")
    return {"paused": True}


@router.post("/runtime/resume")
def runtime_resume(request: Request) -> Dict[str, Any]:
    """Resume orchestrator processing."""
    services = getattr(request.app.state, "services", None)
    orch = getattr(services, "engine_orchestrator", None) if services else None
    if orch is None:
        raise HTTPException(status_code=503, detail="orchestrator not available")
    try:
        orch.is_paused = False
    except Exception:
        raise HTTPException(status_code=500, detail="failed to resume orchestrator")
    return {"paused": False}


# ------------------------------------------------------------------
# Multi-orchestrator control (Batch 1)
# ------------------------------------------------------------------


@router.post("/runtime/start")
async def runtime_start(request: Request) -> Dict[str, Any]:
    multi = getattr(request.app.state, "multi_orch", None)
    if multi is None:
        raise HTTPException(status_code=503, detail="multi orchestrator not configured")
    logger.info("runtime_start_request")
    await multi.start_all()
    return {"status": "started", "symbols": multi.symbols}


@router.post("/runtime/stop")
async def runtime_stop(request: Request) -> Dict[str, Any]:
    multi = getattr(request.app.state, "multi_orch", None)
    if multi is None:
        raise HTTPException(status_code=503, detail="multi orchestrator not configured")
    logger.info("runtime_stop_request")
    await multi.stop_all()
    return {"status": "stopped", "symbols": multi.symbols}


@router.get("/runtime/status")
async def runtime_status(request: Request) -> Dict[str, Any]:
    multi = getattr(request.app.state, "multi_orch", None)
    if multi is None:
        raise HTTPException(status_code=503, detail="multi orchestrator not configured")
    # Build an enriched status payload that includes per-engine risk telemetry.
    out: Dict[str, Any] = {}
    try:
        for sym, orch in getattr(multi, "_orchs", {}).items():
            eng = getattr(orch, "engine", None)
            out[sym] = {
                "paused": getattr(orch, "is_paused", False),
                "last_signal": str(getattr(eng, "last_signal", None)),
                "last_regime": str(getattr(eng, "last_regime", None)),
                # Risk v2 telemetry
                "risk_v2_enabled": getattr(eng, "risk_v2_enabled", False),
                "drawdown": float(getattr(eng, "current_drawdown", 0)),
                "max_equity_seen": float(getattr(eng, "max_equity_seen", 0)),
                "loss_streak": int(getattr(eng, "_loss_streak", 0)),
                "risk_off": bool(getattr(eng, "risk_off", False)),
                "global_risk_off": bool(getattr(eng, "global_risk_off", False)),
                "per_symbol_limit": float(getattr(eng, "per_symbol_exposure_limit", 0)),
                "portfolio_limit": float(getattr(eng, "global_portfolio_limit", 0)),
            }
    except Exception:
        # Fallback to the original status map when enrichment fails
        st = multi.status()
        logger.info("runtime_status_request", extra={"status": st})
        return cast(Dict[str, Any], st)

    logger.info("runtime_status_request", extra={"status": out})
    return out


@router.get("/runtime/sentiment")
def runtime_sentiment() -> Dict[str, Any]:
    from core.runtime_state import read_news_multiplier

    mul = read_news_multiplier()
    return {"sentiment_multiplier": mul}


# ------------------------------------------------------------
# Batch 8 — Prometheus /metrics
# ------------------------------------------------------------
@router.get("/metrics")
def prometheus_metrics(request: Request) -> Response:
    """
    Batch 8 — Prometheus-compatible metrics exporter.
    scrapes:
      - orchestrator metrics
      - per-symbol engine metrics
      - kill switch
    """
    # Prefer a proper Prometheus registry when available. This module is
    # optional so fall back to the existing flat-dict exporter.
    from api.routes import metrics as _metrics

    text = ""
    try:
        # Ensure registry and families exist so we can set runtime values like uptime
        try:
            _metrics.get_registry()
        except Exception:
            pass

        # set uptime gauge if present
        try:
            import time

            start_ts = getattr(request.app.state, "start_ts", None)
            if start_ts is not None:
                try:
                    gauge = getattr(_metrics, "aet_uptime_seconds_total", None)
                    if gauge is not None and hasattr(gauge, "set"):
                        try:
                            gauge.set(float(time.time() - float(start_ts)))
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass

        text = _metrics.generate_metrics_text()
    except Exception:
        text = ""

    if text:
        return Response(text, media_type="text/plain")

    services = getattr(request.app.state, "services", None)
    orch = getattr(services, "engine_orchestrator", None) if services else None

    if orch is None:
        return Response("kill_switch 1\n", media_type="text/plain")

    metrics = orch.prometheus_metrics()
    txt = prometheus_format(metrics)
    return Response(txt, media_type="text/plain")

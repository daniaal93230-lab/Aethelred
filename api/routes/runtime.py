from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
import os
from core.runtime_state import RUNTIME_DIR
from fastapi.responses import JSONResponse

router = APIRouter()


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


@router.get("/runtime/account_runtime.json")
def account_runtime(request: Request) -> Dict[str, Any]:
    app = request.app
    engine = getattr(app.state, "engine", None)
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
        eq_candidates.append(_dict_list(maybe, "equity"))
    except Exception:
        pass
    eq_first = _first_non_empty_list(*eq_candidates)
    if isinstance(eq_first, list):
        equity_series = eq_first

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
        if not equity_series or not positions:
            snap_path = RUNTIME_DIR / "account_runtime.json"
            if snap_path.exists():
                raw = json.loads(snap_path.read_text(encoding="utf-8"))
                if not equity_series:
                    if isinstance(raw.get("equity"), list):
                        equity_series = raw.get("equity")
                    elif raw.get("equity_now") is not None:
                        equity_series = [{"ts": raw.get("ts"), "equity": _safe_float(raw.get("equity_now"))}]
                if not positions and isinstance(raw.get("positions"), list):
                    positions = raw.get("positions")
    except Exception:
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

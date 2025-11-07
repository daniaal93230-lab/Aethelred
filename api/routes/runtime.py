from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

router = APIRouter()


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

    # equity history if engine keeps it
    eq_hist = getattr(engine, "equity_history", None) or getattr(engine, "equity_series", None)
    if isinstance(eq_hist, list):
        eq_rows: List[Dict[str, Any]] = []
        for row in eq_hist:
            ts = row.get("ts") if isinstance(row, dict) else None
            eq = row.get("equity") if isinstance(row, dict) else None
            if ts is None or eq is None:
                continue
            eq_rows.append({"ts": ts, "equity": _safe_float(eq)})
        out["equity"] = eq_rows

    # open positions
    pos_list = getattr(engine, "positions", None) or getattr(engine, "open_positions", None)
    if isinstance(pos_list, list):
        rows: List[Dict[str, Any]] = []
        for p in pos_list:
            # Support both dict-like and object-like positions
            get = p.get if hasattr(p, "get") else lambda k, d=None: getattr(p, k, d)
            sel = get("selector", {}) if hasattr(p, "get") else getattr(p, "selector", {}) or {}
            rows.append(
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
        out["positions"] = rows

    return out


@router.get("/runtime/account_runtime.json")
def runtime_account_runtime_json(request: Request) -> JSONResponse:
    app = request.app
    engine = getattr(app.state, "engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="engine not attached")
    snap = _build_snapshot(engine)
    return JSONResponse(snap)

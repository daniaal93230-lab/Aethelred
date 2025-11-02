from __future__ import annotations
import os
import sqlite3
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException

from analytics.metrics import compute_all_metrics

router = APIRouter(prefix="/insight", tags=["insight"])


def _resolve_db_path(app_state: Optional[object]) -> Optional[str]:
    """
    Resolve a SQLite db path for the journal.
    Priority:
      1) If app.state has attribute journal_db_path
      2) ENV JOURNAL_DB_PATH
      3) data/journal.db if it exists
    Returns None if nothing is found.
    """
    # 1) app.state provided path
    if app_state is not None and hasattr(app_state, "journal_db_path"):
        path = getattr(app_state, "journal_db_path")
        if isinstance(path, str) and path:
            return path
    # 2) env
    env_path = os.getenv("JOURNAL_DB_PATH", "").strip()
    if env_path:
        return env_path
    # 3) default file
    default_path = os.path.join("data", "journal.db")
    if os.path.exists(default_path):
        return default_path
    return None


def _open_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/metrics", summary="Compute and return performance metrics JSON")
def insight_metrics() -> Dict[str, Any]:
    """
    Returns a compact dict with Sharpe, Sortino, MaxDD, Win rate, Expectancy,
    average exposure and average turnover computed from the journal DB.
    """
    # access global app instance through router dependency - FastAPI injects request
    # we avoid a hard dependency here by opening the db via resolved path
    try:
        # FastAPI passes request implicitly, but we keep the signature simple
        # so we fetch it from context using a trick via starlette context if present
        from starlette_context import context as _ctx  # type: ignore

        app_state = getattr(_ctx.data.get("request"), "app", None).state if _ctx and "request" in _ctx.data else None
    except Exception:
        app_state = None

    db_path = _resolve_db_path(app_state)
    if not db_path:
        raise HTTPException(status_code=503, detail="Journal DB not configured or not found")
    if not os.path.exists(db_path):
        raise HTTPException(status_code=503, detail=f"Journal DB path not found: {db_path}")

    try:
        with _open_conn(db_path) as conn:
            metrics = compute_all_metrics(conn)
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"SQLite error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Metrics computation failed: {e}")

    return {"ok": True, "db_path": db_path, "metrics": metrics}

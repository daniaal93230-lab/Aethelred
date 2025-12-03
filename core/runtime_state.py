from __future__ import annotations
from pathlib import Path
import os
from typing import Any, Dict
import json
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
# allow override, else co-locate under project root
RUNTIME_DIR = Path(os.getenv("AET_RUNTIME_DIR", str(ROOT / "runtime"))).resolve()
RUNTIME_DIR.mkdir(exist_ok=True)
KILL_FILE = RUNTIME_DIR / "killswitch.on"

STATE_FILE = RUNTIME_DIR / "state.json"

# ------------------------------------------------------------
# Batch 7 — Telemetry ring buffer
# ------------------------------------------------------------
_EVENTS: list[dict[str, Any]] = []
_EVENT_LIMIT = 50


def record_event(kind: str, payload: dict[str, Any] | None = None) -> None:
    """
    Append a telemetry event (bounded ring buffer).
    kind could be: cycle, train, exception, snapshot, orchestrator.
    """
    entry = {
        "ts": _now_iso(),
        "kind": kind,
        "payload": payload or {},
    }
    _EVENTS.append(entry)
    # enforce ring limit
    if len(_EVENTS) > _EVENT_LIMIT:
        del _EVENTS[0 : len(_EVENTS) - _EVENT_LIMIT]


def read_events() -> list[dict[str, Any]]:
    """Return recent telemetry events."""
    return list(_EVENTS)

# ------------------------------------------------------------
# Batch 8 — Prometheus formatting helper
# ------------------------------------------------------------
def prometheus_format(metrics: dict[str, float | int | str | None]) -> str:
    """
    Convert a flat dict into Prometheus text format.
    All values converted to numbers; strings become 0/1 flags if possible.
    """
    lines = []
    for key, val in metrics.items():
        if val is None:
            continue
        try:
            v = float(val)
        except Exception:
            # Non-numeric → convert truthiness to 0/1
            v = 1.0 if bool(val) else 0.0
        key_safe = key.replace(".", "_").replace("-", "_")
        lines.append(f"{key_safe} {v}")
    return "\n".join(lines) + "\n"

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def write_last(symbol: str, payload: Dict[str, Any]) -> None:
    """
    Persist a simple last-known snapshot by symbol.
    File: runtime/<symbol_sanitized>_runtime.json
    """
    sym = symbol.replace("/", "_")
    out = {
        "ts": _now_iso(),
        "symbol": symbol,
        **payload,
    }
    path = RUNTIME_DIR / f"{sym}_runtime.json"
    # optional: one-time log for sanity when env is set
    if os.getenv("AET_RUNTIME_LOG_PATH_ONCE", "1") == "1":
        # create a sentinel so we do not spam logs each tick
        sentinel = RUNTIME_DIR / ".path_logged"
        if not sentinel.exists():
            # avoid import loop; simple print is fine
            print(f"[runtime_state] writing snapshots to: {RUNTIME_DIR}")
            sentinel.write_text("ok", encoding="utf-8")
    path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def build_engine_snapshot(engine: Any, symbol: str) -> dict:
    """Return a small dict representing the engine runtime state including
    risk telemetry. This is a best-effort helper used by higher-level
    snapshot writers and dashboards.
    """
    snap = {
        "symbol": symbol,
        "last_signal": str(engine.last_signal) if hasattr(engine, "last_signal") else None,
        "last_regime": str(engine.last_regime) if hasattr(engine, "last_regime") else None,
        "risk_v2_enabled": getattr(engine, "risk_v2_enabled", False),
        # Risk v2 telemetry (Phase 3.G)
        "drawdown": float(getattr(engine, "current_drawdown", 0)),
        "max_equity_seen": float(getattr(engine, "max_equity_seen", 0)),
        "loss_streak": int(getattr(engine, "_loss_streak", 0)),
        "risk_off": bool(getattr(engine, "risk_off", False)),
        "global_risk_off": bool(getattr(engine, "global_risk_off", False)),
        "per_symbol_limit": float(getattr(engine, "per_symbol_exposure_limit", 0)),
        "portfolio_limit": float(getattr(engine, "global_portfolio_limit", 0)),
        # ML meta-signal fields
        "ml_score": getattr(engine, "last_ml_score", None),
        "ml_action": getattr(engine, "last_ml_action", None),
        "ml_effective_size": getattr(engine, "last_ml_effective_size", None),
    }
    return snap

def read_news_multiplier(default: float = 1.0) -> float:
    """
    Read runtime/news_state.json and return a safe multiplier in [0.5, 1.5].
    """
    try:
        p = RUNTIME_DIR / "news_state.json"
        if not p.exists():
            return float(default)
        raw = p.read_text(encoding="utf-8-sig")
        mul = float(json.loads(raw).get("multiplier", default))
        return float(max(0.5, min(1.5, mul)))
    except Exception:
        return float(default)


# ------------------------------------------------------------
# Kill-switch helpers (Batch 6D)
# ------------------------------------------------------------

def kill_is_on() -> bool:
    return KILL_FILE.exists()


def kill_on() -> None:
    KILL_FILE.write_text("1", encoding="utf-8")


def kill_off() -> None:
    if KILL_FILE.exists():
        KILL_FILE.unlink()

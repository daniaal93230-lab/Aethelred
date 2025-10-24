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

import json
import time
from pathlib import Path
from typing import Any, Dict, cast


def _load_runtime(cfg: Dict[str, Any]) -> Dict[str, Any]:
    p = Path(cfg["mtm"]["equity_source"]).expanduser()
    data = json.loads(p.read_text())
    return cast(Dict[str, Any], data)


def load_runtime_equity(cfg: Dict[str, Any]) -> float:
    data = _load_runtime(cfg)
    return float(data.get("equity_usd") or data.get("equity") or 0.0)


def compute_exposure_snapshot(cfg: Dict[str, Any]) -> Dict[str, Any]:
    data = _load_runtime(cfg)
    by_symbol: Dict[str, float] = {
        pos["symbol"]: abs(float(pos.get("notional_usd") or pos.get("notional") or 0.0))
        for pos in data.get("positions", [])
        if isinstance(pos, dict) and pos.get("symbol")
    }
    return {
        "portfolio_usd": float(sum(by_symbol.values())),
        "by_symbol": by_symbol,
    }


def is_heartbeat_stale(cfg: Dict[str, Any]) -> bool:
    data = _load_runtime(cfg)
    last_hb = float(data.get("heartbeat_ts", 0))
    stale = (time.time() - last_hb) > float(cfg["mtm"].get("stale_seconds", 60))
    misses = int(data.get("heartbeat_misses", 0))
    return bool(stale or (misses >= int(cfg["mtm"].get("stale_heartbeat_misses_for_flatten", 2))))

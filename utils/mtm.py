import json
import time
from pathlib import Path


def _load_runtime(cfg):
    p = Path(cfg["mtm"]["equity_source"]).expanduser()
    data = json.loads(p.read_text())
    return data


def load_runtime_equity(cfg) -> float:
    data = _load_runtime(cfg)
    return float(data.get("equity_usd") or data.get("equity") or 0.0)


def compute_exposure_snapshot(cfg):
    data = _load_runtime(cfg)
    by_symbol = {
        pos["symbol"]: abs(float(pos.get("notional_usd") or pos.get("notional") or 0.0))
        for pos in data.get("positions", [])
    }
    return {
        "portfolio_usd": float(sum(by_symbol.values())),
        "by_symbol": by_symbol,
    }


def is_heartbeat_stale(cfg) -> bool:
    data = _load_runtime(cfg)
    last_hb = float(data.get("heartbeat_ts", 0))
    stale = (time.time() - last_hb) > float(cfg["mtm"].get("stale_seconds", 60))
    misses = int(data.get("heartbeat_misses", 0))
    return bool(stale or (misses >= int(cfg["mtm"].get("stale_heartbeat_misses_for_flatten", 2))))

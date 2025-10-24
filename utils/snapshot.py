import json
import os
import tempfile
from typing import Any, Dict

RUNTIME_SNAPSHOT_PATH = os.getenv("ACCOUNT_RUNTIME_PATH", "runtime/account_runtime.json")


def _atomic_write(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".snap-", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        finally:
            raise


def write_runtime_snapshot(account_overview: Dict[str, Any]) -> None:
    """
    Persist a small JSON the dashboard can poll quickly.
    Expected keys inside account_overview:
      equity_now, total_notional, positions_by_symbol, positions, pnl_unrealized_pct
    """
    payload = {
        "equity_now": float(account_overview.get("equity_now", 0.0)),
        "total_notional": float(account_overview.get("total_notional", 0.0)),
        "pnl_unrealized_pct": float(account_overview.get("pnl_unrealized_pct", 0.0)),
        "positions": account_overview.get("positions", []),
        "ts": account_overview.get("ts"),
    }
    _atomic_write(RUNTIME_SNAPSHOT_PATH, payload)


# Backwards-compatible helper: previous code wrote equity and positions separately
def write_runtime_snapshot_legacy(equity_usd: float, positions: list, extra: dict | None = None):
    acct = {
        "equity_now": float(equity_usd),
        "positions": positions,
        "ts": extra.get("ts") if extra else None,
        "total_notional": extra.get("total_notional") if extra else 0.0,
    }
    if extra:
        acct.update(extra)
    write_runtime_snapshot(acct)

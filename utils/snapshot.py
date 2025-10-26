import json
from pathlib import Path
from typing import Dict, Any, List

SNAPSHOT_PATH = Path("account_runtime.json")


def _position_view(pos) -> Dict[str, Any]:
    # pos expected fields: symbol, qty, entry, side, mark
    # mtm pnl percent computed as (mark - entry) / entry for long, inverse for short
    entry = pos.get("entry")
    mark = pos.get("mark")
    side = pos.get("side")
    pnl_pct = None
    try:
        if entry and mark and float(entry) != 0.0:
            delta = (float(mark) - float(entry)) / float(entry)
            if side == "short":
                delta = -delta
            pnl_pct = round(delta * 100.0, 4)
    except Exception:
        pnl_pct = None
    return {
        "symbol": pos.get("symbol"),
        "qty": pos.get("qty"),
        "entry": entry,
        "side": side,
        "mark": mark,
        "mtm_pnl_pct": pnl_pct,
    }


def write_runtime_snapshot(obj, extra: Dict[str, Any] | None = None) -> None:
    """
    Preferred: pass an engine that implements account_snapshot().
    Backward compatible: if obj is a dict, write it directly with mtm enrich when possible.
    """
    if hasattr(obj, "account_snapshot"):
        acct = obj.account_snapshot()
    elif isinstance(obj, dict):
        acct = obj
    else:
        acct = {}
    positions: List[Dict[str, Any]] = [_position_view(p) for p in acct.get("positions", [])]
    snapshot = {
        "ts": acct.get("ts"),
        "equity_now": acct.get("equity_now"),
        "total_notional_usd": acct.get("total_notional_usd"),
        "positions": positions,
    }
    if extra:
        snapshot.update(extra)
    SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2))

from __future__ import annotations
from typing import Optional
from db.db_manager import DBManager

def veto_after_winner(symbol: str, db: Optional[DBManager]) -> Optional[str]:
    """
    Returns a veto reason if last closed trade for this symbol was a winner; else None.
    """
    if db is None:
        return None
    try:
        last = db.fetch_last_closed_trade(symbol)
    except Exception:
        return None
    if not last:
        return None
    try:
        pnl = float(last.get("pnl_usd", 0.0) or 0.0)
    except Exception:
        pnl = 0.0
    return "trade_dep" if pnl > 0 else None

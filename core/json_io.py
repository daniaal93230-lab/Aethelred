# json_io.py
"""
Utilities for emitting signals and performance data to JSON files.
"""
import json
import pandas as pd
from typing import Dict, Optional
import json

def emit_signal_to_json(decision: dict, path: str, user=None, equity_curve=None, paper_summary=None):
    payload = {"decision": decision}
    if user is not None:
        payload["user"] = user
    if equity_curve is not None:
        payload["equity_curve"] = [(str(ts), float(val)) for ts, val in equity_curve.items()]
    if paper_summary is not None:
        payload["paper_summary"] = paper_summary
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def emit_signal_to_json(decision: Dict, filepath: str, user: Optional[str] = None,
                        equity_curve: Optional[pd.Series] = None, paper_summary: Optional[Dict] = None) -> None:
    """
    Save the trading decision (and additional info) to a JSON file.
    Optionally inject user ID, full equity performance, and paper trading summary before writing.
    """
    # Inject user ID if provided and not already present
    if user and "user" not in decision:
        decision["user"] = user
    # Add performance summary if full equity curve is given
    if equity_curve is not None and len(equity_curve) > 1:
        # Compute total return percentage over full equity curve
        total_return = (equity_curve.iloc[-1] / max(1e-12, equity_curve.iloc[0]) - 1.0) * 100.0
        decision.setdefault("performance", {}).update({
            "total_return_pct_full_equity": float(total_return)
        })
    # Include paper trading summary if provided
    if paper_summary is not None:
        decision.setdefault("paper", {}).update(paper_summary)
    # Write decision dict to JSON file
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(decision, f, indent=2, default=str)
    print(f"[Brain] JSON signal written to {filepath}")

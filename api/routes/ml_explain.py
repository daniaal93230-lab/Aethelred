from __future__ import annotations

from fastapi import APIRouter, HTTPException
from typing import Optional

from core.ml.explain import ExplainabilityEngine

router = APIRouter()
explainer = ExplainabilityEngine()


@router.get("/ml/explain_signal/{ts}")
def explain_signal(ts: str, mode: Optional[str] = "json"):
    """
    Explains the signal at timestamp {ts}.
    Caller must supply ts that exists in runtime snapshots.
    """
    # Runtime snapshot location
    snap_path = f"runtime/{ts}.json"

    import os, json

    if not os.path.exists(snap_path):
        raise HTTPException(status_code=404, detail="Snapshot not found.")

    try:
        with open(snap_path, "r") as fh:
            snapshot = json.load(fh)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to read snapshot.")

    # Build data dict for features
    data = {
        "signal_strength": snapshot.get("last_strength", 0),
        "regime": snapshot.get("last_regime"),
        "volatility": snapshot.get("volatility"),
        "donchian": snapshot.get("donchian"),
        "ma": snapshot.get("ma"),
        "rsi": snapshot.get("rsi"),
        "intent_veto": snapshot.get("intent"),
    }

    if mode == "plot":
        return {"image_base64": explainer.explain_plot(data)}

    return explainer.explain_json(data)

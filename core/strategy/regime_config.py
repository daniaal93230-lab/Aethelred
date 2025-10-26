from __future__ import annotations
import os
from typing import Dict, Tuple

def load_regime_map(path: str) -> Tuple[str, Dict[str, str]]:
    """
    Reads a simple YAML config with:
      defaults:
        regime: trending
      overrides:
        BTCUSDT: trending
        ETHUSDT: mean_revert
    Returns (default_regime, {symbol: regime})
    Accepts .yaml/.yml; if PyYAML is missing or file not found, returns safe fallbacks.
    """
    default_regime = "unknown"
    mapping: Dict[str, str] = {}
    if not path or not os.path.exists(path):
        return default_regime, mapping
    try:
        import yaml  # type: ignore
    except Exception:
        # If YAML reader is not available, fail safe
        return default_regime, mapping
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
        defaults = doc.get("defaults") or {}
        default_regime = str(defaults.get("regime") or default_regime)
        overrides = doc.get("overrides") or {}
        for k, v in overrides.items():
            if not k:
                continue
            mapping[str(k).upper()] = str(v)
    except Exception:
        # Fail safe on any parse error
        default_regime = "unknown"
        mapping = {}
    return default_regime, mapping

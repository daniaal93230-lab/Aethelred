import os
import copy
from typing import Dict, Any

import yaml  # type: ignore[import-untyped]

_CACHE: Dict[str, Any] = {}
_MTIME: float = 0.0

PROFILES: Dict[str, Dict[str, Any]] = {
    "conservative": {
        "daily_loss_limit_pct": 2.0,
        "per_trade_risk_pct": 0.35,
        "max_leverage": 1.2,
        "exposure": {"set_as_fraction": True, "max_exposure_usd": 0.25, "per_symbol_exposure_pct": 0.15},
    },
    "standard": {
        "daily_loss_limit_pct": 3.0,
        "per_trade_risk_pct": 0.50,
        "max_leverage": 1.5,
        "exposure": {"set_as_fraction": True, "max_exposure_usd": 0.35, "per_symbol_exposure_pct": 0.20},
    },
    "aggressive": {
        "daily_loss_limit_pct": 5.0,
        "per_trade_risk_pct": 0.75,
        "max_leverage": 2.0,
        "exposure": {"set_as_fraction": True, "max_exposure_usd": 0.50, "per_symbol_exposure_pct": 0.30},
    },
}


def _merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)  # type: ignore[index]
        else:
            out[k] = v
    return out


def load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


def _apply_profile(base: Dict[str, Any], profile: str) -> Dict[str, Any]:
    prof = PROFILES.get(profile, PROFILES["standard"])
    return _merge(base, prof)


def _flatten_compat(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten the new nested risk schema into legacy keys expected by the codebase.

    - Supports both legacy (flat) and new (nested under meta/limits/ops) formats.
    - Returns a dict that still contains original nested keys for future usage,
      but guarantees legacy keys exist: kill_switch, daily_loss_limit_pct,
      per_trade_risk_pct, exposure{set_as_fraction,max_exposure_usd,per_symbol_exposure_pct},
      max_leverage.
    """
    out: Dict[str, Any] = copy.deepcopy(raw)
    is_new = isinstance(raw.get("limits"), dict) or isinstance(raw.get("meta"), dict) or isinstance(raw.get("mtm"), dict)
    if not is_new:
        # legacy format already
        return out

    limits = raw.get("limits", {}) or {}
    ops = raw.get("ops", {}) or {}

    # kill_switch default from nested ops if top-level not present
    if "kill_switch" not in out:
        ks_default = (ops.get("kill_switch", {}) or {}).get("default", "off")
        out["kill_switch"] = True if str(ks_default).lower() in {"on", "true", "1"} else False

    # daily_loss_limit_pct: prefer hard threshold
    dll = limits.get("daily_loss_limit_pct")
    if isinstance(dll, dict):
        hard = dll.get("hard")
        soft = dll.get("soft")
        if hard is not None:
            out["daily_loss_limit_pct"] = float(hard)
        elif soft is not None:
            out["daily_loss_limit_pct"] = float(soft)
    elif dll is not None:
        out["daily_loss_limit_pct"] = float(dll)

    # per_trade_risk_pct: prefer hard
    ptr = limits.get("per_trade_risk_pct")
    if isinstance(ptr, dict):
        hard = ptr.get("hard")
        soft = ptr.get("soft")
        if hard is not None:
            out["per_trade_risk_pct"] = float(hard)
        elif soft is not None:
            out["per_trade_risk_pct"] = float(soft)
    elif ptr is not None:
        out["per_trade_risk_pct"] = float(ptr)

    # exposure mapping: support both prior nested and the new requested keys
    exp = limits.get("max_exposure_usd")
    mode = str(limits.get("max_exposure_mode", "dynamic")).lower()
    per_sym_default = (raw.get("exposure", {}) or {}).get("per_symbol_exposure_pct", 0.20)
    if isinstance(exp, dict):
        mode = str(exp.get("mode", mode)).lower()
        if mode == "dynamic":
            frac = (exp.get("dynamic", {}) or {}).get("equity_fraction_cap", limits.get("max_exposure_pct_equity", 35))
            out["exposure"] = {
                "set_as_fraction": True,
                "max_exposure_usd": float(frac) / (100.0 if float(frac) > 1.0 else 1.0),
                "per_symbol_exposure_pct": float(per_sym_default if per_sym_default <= 1 else per_sym_default / 100.0),
            }
        else:
            val = exp.get("static_value_usd", limits.get("max_exposure_usd", 0.0))
            out["exposure"] = {
                "set_as_fraction": False,
                "max_exposure_usd": float(val),
                "per_symbol_exposure_pct": float(per_sym_default if per_sym_default <= 1 else per_sym_default / 100.0),
            }
    elif exp is not None:
        # treat as absolute USD cap if a number is provided
        out["exposure"] = {
            "set_as_fraction": False,
            "max_exposure_usd": float(exp),
            "per_symbol_exposure_pct": float(per_sym_default if per_sym_default <= 1 else per_sym_default / 100.0),
        }
    else:
        # no explicit exp dict; handle new dynamic fields
        if mode == "dynamic":
            frac = float(limits.get("max_exposure_pct_equity", 35))
            out["exposure"] = {
                "set_as_fraction": True,
                "max_exposure_usd": frac / 100.0,
                "per_symbol_exposure_pct": float(limits.get("max_per_symbol_pct_equity", 20)) / 100.0,
            }

    # leverage: new key is max_gross_leverage, or limits.max_leverage in the dynamic schema
    if "max_leverage" not in out:
        mgl = limits.get("max_gross_leverage", limits.get("max_leverage"))
        if mgl is not None:
            out["max_leverage"] = float(mgl)

    return out


def get_risk_cfg(path: str = "config/risk.yaml") -> Dict[str, Any]:
    global _CACHE, _MTIME
    try:
        st = os.stat(path)
        if not _CACHE or st.st_mtime > _MTIME:
            raw = load_yaml(path)
            # If new nested schema is detected, don't apply profiles; flatten to legacy keys.
            if isinstance(raw.get("limits"), dict) or isinstance(raw.get("meta"), dict):
                merged = _flatten_compat(raw)
            else:
                profile = os.getenv("RISK_PROFILE", raw.get("profile", "standard"))
                merged = _apply_profile(raw, profile)
            _CACHE = merged
            _MTIME = st.st_mtime
    except FileNotFoundError:
        _CACHE = PROFILES["standard"]
    return _CACHE

"""
Risk Reason Taxonomy
--------------------
Minimal and stable enumeration of reasons used across:
 - RiskEngine
 - decision export schema
 - veto, stop, entry/exit annotations
This file must remain minimal and safe.
"""

from __future__ import annotations
from enum import Enum


class Reason(str, Enum):
    # Core trading reasons
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    STOP = "STOP"
    VETO = "VETO"

    # Optional extended reasons (stable names)
    RISK_MAX_EXPOSURE = "RISK_MAX_EXPOSURE"
    RISK_PER_SYMBOL = "RISK_PER_SYMBOL"
    RISK_PER_TRADE = "RISK_PER_TRADE"
    RISK_DAILY_LOSS = "RISK_DAILY_LOSS"
    RISK_LEVERAGE = "RISK_LEVERAGE"

    OPS_KILL_SWITCH = "OPS_KILL_SWITCH"
    OPS_HEALTHZ_STALE = "OPS_HEALTHZ_STALE"
    ML_VETO = "ML_VETO"
    API_ERROR = "API_ERROR"


__all__ = ["Reason"]

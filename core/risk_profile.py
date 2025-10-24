from __future__ import annotations
from dataclasses import dataclass
import os


@dataclass
class RiskProfile:
    name: str
    risk_multiplier: float          # scales base ATR notional (bounded later)
    leverage_max: float
    risk_per_trade_pct: float       # of equity (percent)
    max_daily_loss_pct: float       # DLL; breaker triggers when breached (percent)
    auto_flatten_on_dll: bool
    # Adaptive panic band: ATR multiples threshold before forcing regime panic
    panic_atr_mult: float = 3.0


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def pick_profile(equity_usd: float) -> RiskProfile:
    """
    Auto-pick a sensible risk profile by equity size.
    Env overrides (optional) take precedence:
      RISK_MULTIPLIER, LEVERAGE_MAX, RISK_PER_TRADE_PCT, RISK_MAX_DAILY_LOSS_PCT, AUTO_FLATTEN_ON_DLL
    """
    # defaults by equity bucket
    if equity_usd < 500:
        base = RiskProfile(
            name="aggressive",
            risk_multiplier=1.6,
            leverage_max=3.0,
            risk_per_trade_pct=1.0,
            max_daily_loss_pct=5.0,
            auto_flatten_on_dll=True,
            panic_atr_mult=5.0,
        )
    elif equity_usd < 5000:
        base = RiskProfile(
            name="balanced",
            risk_multiplier=1.2,
            leverage_max=2.5,
            risk_per_trade_pct=0.5,
            max_daily_loss_pct=3.0,
            auto_flatten_on_dll=True,
            panic_atr_mult=4.0,
        )
    else:
        base = RiskProfile(
            name="conservative",
            risk_multiplier=1.0,
            leverage_max=2.0,
            risk_per_trade_pct=0.25,
            max_daily_loss_pct=2.0,
            auto_flatten_on_dll=True,
            panic_atr_mult=3.0,
        )

    # optional env overrides
    rm = float(os.getenv("RISK_MULTIPLIER", base.risk_multiplier))
    lev = float(os.getenv("LEVERAGE_MAX", base.leverage_max))
    rpt = float(os.getenv("RISK_PER_TRADE_PCT", base.risk_per_trade_pct))
    dll = float(os.getenv("RISK_MAX_DAILY_LOSS_PCT", base.max_daily_loss_pct))
    afd = os.getenv("AUTO_FLATTEN_ON_DLL", "true").lower() in ("1", "true", "yes", "on")

    return RiskProfile(
        name=base.name,
        risk_multiplier=_clamp(rm, 0.5, 3.0),
        leverage_max=_clamp(lev, 1.0, 5.0),
        risk_per_trade_pct=_clamp(rpt, 0.05, 2.0),
        max_daily_loss_pct=_clamp(dll, 0.5, 10.0),
        auto_flatten_on_dll=afd,
        panic_atr_mult=base.panic_atr_mult,
    )

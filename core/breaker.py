from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timedelta, timezone

@dataclass
class BreakerConfig:
    max_intraday_dd_pct: float = 0.03   # 3 percent
    panic_vol_z_gate: float = 2.5
    cooldown_sec: int = 900
    # NEW: daily loss limit (percentage of start-of-day equity)
    max_daily_loss_pct: float = 0.03
    auto_flatten_on_dll: bool = True

@dataclass
class BreakerState:
    day_start_equity: float = 0.0
    trail_peak: float = 0.0
    active: bool = False
    cooldown_until: Optional[datetime] = None
    # NEW: reason tracking
    last_reason: Optional[str] = None

def _now() -> datetime:
    return datetime.now(timezone.utc)

def start_of_day(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

def update_breaker(state: BreakerState, equity: float, regime_label: str, cfg: BreakerConfig) -> BreakerState:
    now = _now()
    # reset day anchor if new UTC day
    if state.day_start_equity <= 0.0 or start_of_day(now) > start_of_day(state.cooldown_until or now):
        state.day_start_equity = equity
        state.trail_peak = max(state.trail_peak, equity)

    state.trail_peak = max(state.trail_peak, equity)
    intraday_dd = 0.0
    if state.day_start_equity > 0:
        intraday_dd = (state.day_start_equity - equity) / state.day_start_equity

    # Activate on drawdown or panic regime
    if intraday_dd >= cfg.max_intraday_dd_pct or regime_label == "panic":
        state.active = True
        state.cooldown_until = now + timedelta(seconds=cfg.cooldown_sec)
        state.last_reason = "intraday_dd" if intraday_dd >= cfg.max_intraday_dd_pct else "panic"
        return state

    # NEW: Daily loss limit vs start-of-day equity
    if state.day_start_equity > 0 and cfg.max_daily_loss_pct > 0:
        day_down = (state.day_start_equity - equity) / state.day_start_equity
        if day_down >= cfg.max_daily_loss_pct:
            state.active = True
            state.cooldown_until = now + timedelta(seconds=cfg.cooldown_sec)
            state.last_reason = "daily_loss"
            return state

    # Deactivate when cooldown passes
    if state.active and state.cooldown_until and now >= state.cooldown_until:
        state.active = False
        state.trail_peak = equity
        state.last_reason = None
    return state

# risk.py
"""
Risk management and position sizing functions, including Kelly criterion calculations for sizing trades.
"""
from dataclasses import dataclass
from typing import Dict, Optional, Any
import math
import pandas as pd

def kelly_fraction(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """
    Calculate the Kelly fraction given win probability, average win, and average loss.
    Returns the fraction of capital to risk. Returns 0.0 if inputs are invalid or no edge (e.g., non-positive loss or zero expectancy).
    """
    if avg_loss <= 0 or (avg_win + avg_loss) == 0:
        return 0.0
    b = avg_win / abs(avg_loss)
    p = max(0.0, min(1.0, win_rate))
    q = 1.0 - p
    # Kelly formula: optimal fraction = (b * p - q) / b
    k = (b * p - q) / b
    return max(0.0, k)

def kelly_from_trades(expectancy: float, win_rate: float, shrink: float = 20.0) -> float:
    """
    Approximate the Kelly fraction from expectancy and win rate, using a shrinkage factor to reduce position size.
    Uses a heuristic that assumes average win is ~2 * |average loss| for estimating Kelly fraction.
    """
    p = max(0.0, min(1.0, win_rate))
    denom = max(1e-6, (3 * p - 1.0))
    avg_loss = expectancy / denom if denom != 0 else 0.0
    avg_win = 2.0 * avg_loss
    return float(kelly_fraction(p, avg_win, avg_loss) / max(1.0, shrink))

def clip(value: float, lo: float, hi: float) -> float:
    """Clamp a value between lo and hi inclusive."""
    return max(lo, min(hi, value))

def kelly_size_from_metrics(met_tr: Dict, kelly_on: bool, kelly_min: float,
                             kelly_max: float, kelly_shrink: float, base_risk: float) -> float:
    """
    Determine a position size fraction based on metrics (e.g., training results) and Kelly criterion parameters.
    - If kelly_on is False, return base_risk unchanged.
    - If kelly_on is True, compute a Kelly fraction from metrics, apply shrinkage and clamp between kelly_min and kelly_max (scaled by base_risk).
    """
    if not kelly_on:
        return float(base_risk)
    p = float(met_tr.get("win_rate", 0.0))
    E = float(met_tr.get("expectancy", 0.0))
    k = kelly_from_trades(E, p, shrink=kelly_shrink)
    k = clip(k, kelly_min * base_risk, kelly_max * base_risk)
    return float(k)

# ================= ATR sizing additions =================
@dataclass
class RiskConfig:
    risk_per_trade_pct: float = 0.002
    atr_lookback: int = 14
    atr_k: float = 1.5
    min_notional_usd: float = 10.0
    max_leverage: float = 2.0
    max_position_usd: float = 2000.0
    max_symbol_gross_exposure_usd: float = 4000.0

def compute_atr(df: pd.DataFrame, n: int) -> pd.Series:
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    c = df["close"].astype(float)
    prev = c.shift(1)
    tr = pd.concat([(h - l).abs(), (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False).mean()

def position_size_usd(
    equity_usd: float,
    price: float,
    atr_latest: Optional[float],
    cfg: RiskConfig,
    leverage_limit: Optional[float] = None,
    existing_symbol_gross_usd: float = 0.0,
) -> float:
    if price <= 0 or equity_usd <= 0:
        return 0.0
    if atr_latest is None or not math.isfinite(atr_latest) or atr_latest <= 0:
        base = min(cfg.min_notional_usd, equity_usd * cfg.risk_per_trade_pct)
        cap = min(base * (leverage_limit or cfg.max_leverage), cfg.max_position_usd)
        remain = max(cfg.max_symbol_gross_exposure_usd - existing_symbol_gross_usd, 0.0)
        return max(0.0, min(cap, remain))
    stop_usd_per_unit = cfg.atr_k * atr_latest
    if stop_usd_per_unit <= 0:
        return 0.0
    risk_budget = equity_usd * cfg.risk_per_trade_pct
    units = risk_budget / stop_usd_per_unit
    notional = units * price
    lev = leverage_limit if leverage_limit is not None else cfg.max_leverage
    notional *= lev
    notional = max(0.0, min(notional, cfg.max_position_usd))
    remain = max(cfg.max_symbol_gross_exposure_usd - existing_symbol_gross_usd, 0.0)
    notional = min(notional, remain)
    if notional < cfg.min_notional_usd:
        return 0.0
    return float(notional)

# ======== New risk gating engine ========
@dataclass
class RiskDecision:
    allow: bool
    reason: str = ""
    details: Dict[str, Any] | None = None


class RiskEngine:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg

    def check(self, acct: Dict[str, Any], order: Dict[str, Any]) -> RiskDecision:
        """
        acct: latest account_overview() with MTM fields
          expected keys: equity_now, total_notional, positions_by_symbol{symbol: {"notional": float}}
        order: proposed order intent with keys:
          symbol, side, qty, notional, est_stop_price (optional), mid_price
        """
        # 1) Kill switch
        if self.cfg.get("kill_switch", False):
            return RiskDecision(False, "kill_switch", {"kill_switch": True})

        equity = float(acct.get("equity_now", 0.0))
        total_notional = float(acct.get("total_notional", 0.0))
        symbol = order.get("symbol")
        order_notional = float(order.get("notional") or (float(order.get("qty", 0.0)) * float(order.get("mid_price", 0.0))))

        # 2) Daily loss breaker
        daily_dd_pct = float(acct.get("drawdown_pct_today", 0.0))
        if daily_dd_pct <= 0.0:
            if abs(daily_dd_pct) >= float(self.cfg.get("daily_loss_limit_pct", 3.0)):
                return RiskDecision(False, "breaker:daily_loss", {"dd_today_pct": daily_dd_pct})

        # 3) Exposure limits
        exposure_cfg = self.cfg.get("exposure", {})
        set_as_fraction = bool(exposure_cfg.get("set_as_fraction", True))
        max_expo_val = float(exposure_cfg.get("max_exposure_usd", 0.35))
        max_exposure_usd = (max_expo_val * equity) if set_as_fraction else max_expo_val
        if total_notional + order_notional > max_exposure_usd:
            return RiskDecision(False, "limit:portfolio_exposure", {
                "total_notional": total_notional,
                "order_notional": order_notional,
                "max_exposure_usd": max_exposure_usd,
            })

        per_sym_cap = float(exposure_cfg.get("per_symbol_exposure_pct", 0.20)) * equity
        sym_notional_now = float((acct.get("positions_by_symbol", {}) or {}).get(symbol, {}).get("notional", 0.0))
        if sym_notional_now + order_notional > per_sym_cap:
            return RiskDecision(False, "limit:per_symbol_exposure", {
                "symbol": symbol,
                "sym_notional_now": sym_notional_now,
                "order_notional": order_notional,
                "cap_usd": per_sym_cap,
            })

        # 4) Leverage
        max_lev = float(self.cfg.get("max_leverage", 1.5))
        if equity > 0 and (total_notional + order_notional) / equity > max_lev:
            return RiskDecision(False, "limit:leverage", {
                "leverage_next": (total_notional + order_notional) / equity,
                "max": max_lev,
            })

        # 5) Per-trade risk sizing sanity
        risk_budget_pct = float(self.cfg.get("per_trade_risk_pct", 0.5)) / 100.0
        est_stop = order.get("est_stop_price")
        if est_stop is not None:
            mid = float(order.get("mid_price", 0.0))
            qty = float(order.get("qty", 0.0))
            if qty > 0 and mid > 0:
                if str(order.get("side", "")).lower() == "buy":
                    est_loss = max(0.0, (mid - float(est_stop))) * qty
                else:
                    est_loss = max(0.0, (float(est_stop) - mid)) * qty
                if est_loss > equity * risk_budget_pct:
                    return RiskDecision(False, "limit:per_trade_risk", {
                        "est_loss": est_loss,
                        "budget_usd": equity * risk_budget_pct,
                    })

        return RiskDecision(True, "ok", {"order_notional": order_notional})

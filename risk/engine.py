"""Compatibility shim for legacy ``risk.engine``.

Expose ``RiskEngine`` from ``core.risk`` when present, otherwise provide a
minimal stub so imports don't fail during tests.
"""

from typing import Any

__all__ = ["RiskEngine"]
from dataclasses import dataclass
from typing import Dict

from .taxonomy import Reason
from .state import RiskKV
from utils.mtm import load_runtime_equity, compute_exposure_snapshot, is_heartbeat_stale
from utils.config import load_risk_cfg, on_risk_cfg_change


@dataclass
class RiskDecision:
    allow: bool
    reason: str = ""
    details: Dict[str, Any] | None = None


class RiskEngine:
    def __init__(self) -> None:
        self.cfg = load_risk_cfg()
        if (self.cfg.get("reload", {}) or {}).get("enabled", False):
            on_risk_cfg_change(self._reload)
        self.kv = RiskKV()

    def _reload(self) -> None:
        self.cfg = load_risk_cfg()

    def status(self) -> Dict[str, Any]:
        return {
            "kill_switch": self.kv.get("kill_switch", "off"),
            "daily_loss_breaker": self.kv.get("daily_loss_breaker", "off"),
            "heartbeat_misses": int(self.kv.get("heartbeat_misses", "0")),
            "config_version": self.cfg.get("version") or self.cfg.get("meta", {}).get("version", 1),
        }

    def set_kill_switch(self, on: bool) -> None:
        self.kv.set("kill_switch", "on" if on else "off")
        # audit hook could be added here

    def reset_breakers(self) -> None:
        self.kv.set("daily_loss_breaker", "off")

    def pre_trade_checks(
        self,
        symbol: str,
        notional_usd: float,
        est_loss_pct_equity: float,
        leverage_after: float,
    ) -> RiskDecision:
        cfg = self.cfg
        equity = load_runtime_equity(cfg)
        exp = compute_exposure_snapshot(cfg)

        if self.kv.get("kill_switch", "off") == "on":
            return RiskDecision(False, Reason.OPS_KILL_SWITCH, {"equity": equity})

        if is_heartbeat_stale(cfg):
            return RiskDecision(False, Reason.OPS_HEALTHZ_STALE, {})

        # portfolio exposure
        limits = cfg.get("limits", {})
        mode = str(limits.get("max_exposure_mode", "dynamic")).lower()
        if mode == "fixed_usd" and float(limits.get("max_exposure_usd", 0)) > 0:
            max_portfolio = float(limits.get("max_exposure_usd", 0))
        else:
            pct = float(limits.get("max_exposure_pct_equity", 65)) / 100.0
            max_portfolio = equity * pct
        if exp["portfolio_usd"] + notional_usd > max_portfolio + 1e-6:
            return RiskDecision(False, Reason.RISK_MAX_EXPOSURE, {"exp": exp, "max_portfolio": max_portfolio})

        # per symbol exposure
        max_sym = equity * (float(limits.get("max_per_symbol_pct_equity", 45)) / 100.0)
        sym_now = float(exp["by_symbol"].get(symbol, 0.0))
        if sym_now + notional_usd > max_sym + 1e-6:
            return RiskDecision(False, Reason.RISK_PER_SYMBOL, {"sym_exp": sym_now, "max_sym": max_sym})

        # leverage
        if leverage_after > float(limits.get("max_leverage", 1.5)) + 1e-9:
            return RiskDecision(False, Reason.RISK_LEVERAGE, {"leverage_after": leverage_after})

        # per trade risk
        if est_loss_pct_equity > float(limits.get("per_trade_risk_pct", 1.25)) + 1e-9:
            return RiskDecision(False, Reason.RISK_PER_TRADE, {"est_loss_pct_equity": est_loss_pct_equity})

        # daily loss breaker state gate
        if self.kv.get("daily_loss_breaker", "off") == "on":
            return RiskDecision(False, Reason.RISK_DAILY_LOSS, {})

        return RiskDecision(True, "ok", {"equity": equity})

    def post_trade_update(self, pnl_day_pct: float) -> None:
        limits = self.cfg.get("limits", {})
        if pnl_day_pct <= -abs(float(limits.get("daily_loss_limit_pct", 4.0))) - 1e-9:
            self.kv.set("daily_loss_breaker", "on")

from __future__ import annotations

from typing import Optional, List
from pydantic import BaseModel, Field


# ---------------------------------------------------------
# Compact Insight summary for per-symbol multi-dashboard
# ---------------------------------------------------------
class InsightMini(BaseModel):
    sharpe: Optional[float] = Field(None, description="Latest rolling sharpe ratio")
    sortino: Optional[float] = Field(None, description="Latest rolling sortino")
    calmar: Optional[float] = Field(None, description="Latest rolling calmar")
    daily_pnl: Optional[float] = Field(None, description="Today's PnL for quick glance")
    active_regime: Optional[str] = Field(None, description="Current regime from selector")
    top_strategy: Optional[str] = Field(None, description="Most profitable strategy today")


# ---------------------------------------------------------
# Compact Risk summary for per-symbol multi-dashboard
# ---------------------------------------------------------
class RiskMini(BaseModel):
    volatility: float = Field(..., description="Symbol realized volatility")
    exposure_usd: float = Field(..., description="Symbol USD exposure")
    sizing_state: str = Field(..., description="Current sizing mode: scaled, normal, zero, panic")
    panic: bool = Field(..., description="Kill-switch status")


# ---------------------------------------------------------
# Per-symbol operational health block
# ---------------------------------------------------------
class OpsMini(BaseModel):
    status: str = Field(..., description="running, paused, stopped, or error")
    last_cycle_ms: Optional[int] = Field(None, description="Duration of last engine cycle")
    stalled: bool = Field(..., description="True if orchestrator detected engine stall")
    last_error: Optional[str] = Field(None, description="Last error message if any")


# ---------------------------------------------------------
# Per-symbol snapshot for multi-dashboard
# ---------------------------------------------------------
class SymbolDashboardRow(BaseModel):
    symbol: str = Field(..., description="Market symbol")

    insight: InsightMini = Field(..., description="Condensed insight state")
    risk: RiskMini = Field(..., description="Condensed risk state")
    ops: OpsMini = Field(..., description="Operational health state")

    alerts: List[str] = Field(
        default_factory=list,
        description="Alert badges derived from symbol state",
    )


# ---------------------------------------------------------
# Portfolio summary block
# ---------------------------------------------------------
class PortfolioDashboard(BaseModel):
    portfolio_volatility: float = Field(..., description="Overall portfolio realized volatility")
    portfolio_exposure_usd: float = Field(..., description="Total exposure across all symbols")
    symbols_active: int = Field(..., description="How many symbols are currently running")
    alerts: List[str] = Field(default_factory=list, description="Portfolio-level alerts")


# ---------------------------------------------------------
# Root multi-symbol dashboard payload
# ---------------------------------------------------------
class MultiSymbolDashboard(BaseModel):
    timestamp: str = Field(..., description="ISO timestamp for snapshot")
    portfolio: PortfolioDashboard = Field(..., description="Portfolio-wide aggregates")
    symbols: List[SymbolDashboardRow] = Field(..., description="Per-symbol compact dashboard rows")

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------
# Risk metrics (symbol + portfolio)
# ---------------------------------------------------------
class RiskMetrics(BaseModel):
    volatility: float = Field(..., description="Symbol realized volatility")
    portfolio_volatility: float = Field(..., description="Realized volatility of total portfolio")
    vol_target_scaling: float = Field(..., description="Scaling factor from VolatilityTargeter")
    panic: bool = Field(..., description="Kill-switch state from RiskEngineV3")

    # Thresholds for UI display
    vol_kill_threshold: Optional[float] = Field(None, description="Symbol-level volatility threshold")
    portfolio_kill_threshold: Optional[float] = Field(None, description="Portfolio-level volatility threshold")


# ---------------------------------------------------------
# Exposure information (symbol + portfolio breakdown)
# ---------------------------------------------------------
class ExposureSlice(BaseModel):
    symbol: str = Field(..., description="Symbol for the slice")
    usd: float = Field(..., description="Exposure for this symbol in USD")


class ExposureBlock(BaseModel):
    symbol_exposure_usd: float = Field(..., description="Total exposure for the symbol in USD")
    portfolio_exposure_usd: float = Field(..., description="Total exposure of the portfolio in USD")
    exposure_ratio: float = Field(..., description="Symbol exposure divided by portfolio exposure")
    exposure_breakdown: List[ExposureSlice] = Field(..., description="Per-symbol exposure list for pie charts")


# ---------------------------------------------------------
# State (regime + sizing mode)
# ---------------------------------------------------------
class RiskState(BaseModel):
    current_regime: str = Field(..., description="ADX/Selector-derived regime: trend, chop, transition")
    sizing_state: str = Field(..., description="Current size state: scaled, normal, zero, panic")
    risk_mode: str = Field(..., description="Operational mode: normal, limit, panic")


# ---------------------------------------------------------
# Position information
# ---------------------------------------------------------
class PositionBlock(BaseModel):
    size: float = Field(..., description="Position size in asset units")
    usd_value: float = Field(..., description="USD notional exposure")
    entry_price: Optional[float] = Field(None, description="Average entry price")
    unrealized_pnl: Optional[float] = Field(None, description="Unrealized PnL in USD")


# ---------------------------------------------------------
# Root Risk Dashboard payload
# ---------------------------------------------------------
class RiskDashboard(BaseModel):
    symbol: str = Field(..., description="Market symbol")
    timestamp: str = Field(..., description="ISO timestamp for snapshot")

    risk: RiskMetrics = Field(..., description="Risk metrics derived from RiskEngineV3")
    exposure: ExposureBlock = Field(..., description="Exposure breakdown for the symbol and portfolio")
    state: RiskState = Field(..., description="Current risk state")
    position: PositionBlock = Field(..., description="Live position snapshot for symbol")

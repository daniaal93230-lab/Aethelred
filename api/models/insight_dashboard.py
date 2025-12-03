from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------
# Rolling metric: simple timestamp/value pair
# ---------------------------------------------------------
class RollingPoint(BaseModel):
    ts: int = Field(..., description="Unix timestamp (seconds)")
    value: float = Field(..., description="Metric value at timestamp")


# ---------------------------------------------------------
# Rolling performance block: Sharpe, Sortino, Calmar, etc
# ---------------------------------------------------------
class RollingPerformance(BaseModel):
    window_trades: int = Field(..., description="Rolling window size in trade count")
    sharpe: List[RollingPoint] = Field(..., description="Rolling Sharpe ratio values")
    sortino: List[RollingPoint] = Field(..., description="Rolling Sortino ratio values")
    calmar: List[RollingPoint] = Field(..., description="Rolling Calmar ratio values")
    equity_curve: List[RollingPoint] = Field(..., description="Rolling equity curve values")


# ---------------------------------------------------------
# Per-strategy MAE/MFE stats
# ---------------------------------------------------------
class StrategyMAEMFE(BaseModel):
    strategy: str = Field(..., description="Strategy name")
    count: int = Field(..., description="Number of closed trades tracked")
    avg_mae: float = Field(..., description="Average Maximum Adverse Excursion")
    avg_mfe: float = Field(..., description="Average Maximum Favorable Excursion")
    win_rate: float = Field(..., description="Win rate for this strategy (0 to 1)")
    median_hold_seconds: int = Field(..., description="Median holding time in seconds")


# ---------------------------------------------------------
# KPI Tile Block
# ---------------------------------------------------------
class KPITiles(BaseModel):
    daily_pnl: float = Field(..., description="Today's realized PnL")
    daily_return_pct: float = Field(..., description="Today's return percent")
    max_drawdown_pct: float = Field(..., description="Maximum drawdown percent for current window")
    trade_count: int = Field(..., description="Number of trades completed today")
    active_regime: str = Field(..., description="Current active regime from selector")
    top_strategy: Optional[str] = Field(None, description="Best performing strategy today")


# ---------------------------------------------------------
# Recent trade record
# ---------------------------------------------------------
class TradeRecord(BaseModel):
    trade_id: str = Field(..., description="Unique trade identifier")
    side: str = Field(..., description="buy or sell")
    strategy: str = Field(..., description="Strategy responsible for trade")

    entry_ts: int = Field(..., description="Entry timestamp (unix seconds)")
    exit_ts: Optional[int] = Field(None, description="Exit timestamp (unix seconds)")

    entry_price: float = Field(..., description="Entry fill price")
    exit_price: Optional[float] = Field(None, description="Exit fill price")

    pnl: Optional[float] = Field(None, description="Realized PnL for the trade")
    mfe: Optional[float] = Field(None, description="Maximum favorable excursion")
    mae: Optional[float] = Field(None, description="Maximum adverse excursion")

    holding_seconds: Optional[int] = Field(None, description="Total holding time in seconds")


# ---------------------------------------------------------
# Root Insight Dashboard payload
# ---------------------------------------------------------
class InsightDashboard(BaseModel):
    symbol: str = Field(..., description="Market symbol (e.g. BTC/USDT)")
    timestamp: str = Field(..., description="ISO timestamp for snapshot creation")

    performance: dict = Field(..., description="Rolling performance metrics (Sharpe, Sortino, Calmar)")

    strategy_mae_mfe: List[StrategyMAEMFE] = Field(..., description="MAE/MFE summary for each active strategy")

    kpis: KPITiles = Field(..., description="KPI tile metrics for dashboard overview")

    recent_trades: List[TradeRecord] = Field(..., description="Most recent closed trades")


# ---------------------------------------------------------
# Helper container used by future builder service
# ---------------------------------------------------------
class InsightPerformanceBlock(BaseModel):
    rolling: RollingPerformance = Field(..., description="Full rolling metrics block for performance charts")

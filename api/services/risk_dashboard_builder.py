from __future__ import annotations

import datetime
from typing import List, Optional

from api.models.risk_dashboard import (
    RiskDashboard,
    RiskMetrics,
    ExposureBlock,
    ExposureSlice,
    RiskState,
    PositionBlock,
)


class RiskDashboardBuilder:
    """
    Builds a complete RiskDashboard snapshot for one symbol.

    Pulls from:
      - RiskEngineV3.risk_telemetry
      - orchestrator exposure model
      - orchestrator last regime and sizing state
      - execution engine position state
    """

    def __init__(
        self,
        symbol: str,
        risk_engine,
        orchestrator,
        engine,
    ):
        self.symbol = symbol
        self.risk_engine = risk_engine
        self.orchestrator = orchestrator
        self.engine = engine

    # -----------------------------------------------------
    # Entry point
    # -----------------------------------------------------
    def build(self) -> RiskDashboard:
        timestamp = datetime.datetime.utcnow().isoformat()

        risk_metrics = self._build_risk_metrics()
        exposure = self._build_exposure_block()
        state = self._build_state_block()
        position = self._build_position_block()

        return RiskDashboard(
            symbol=self.symbol,
            timestamp=timestamp,
            risk=risk_metrics,
            exposure=exposure,
            state=state,
            position=position,
        )

    # -----------------------------------------------------
    # RISK METRICS
    # -----------------------------------------------------
    def _build_risk_metrics(self) -> RiskMetrics:
        """
        Builds volatility, scaling, panic-state and thresholds
        from RiskEngineV3.risk_telemetry.
        """
        telem = getattr(self.risk_engine, "risk_telemetry", None)
        if telem is None:
            # Fully safe fallback
            return RiskMetrics(
                volatility=0.0,
                portfolio_volatility=0.0,
                vol_target_scaling=1.0,
                panic=False,
                vol_kill_threshold=None,
                portfolio_kill_threshold=None,
            )

        return RiskMetrics(
            volatility=float(telem.get("volatility", 0.0)),
            portfolio_volatility=float(telem.get("portfolio_volatility", 0.0)),
            vol_target_scaling=float(telem.get("scaling", 1.0)),
            panic=bool(telem.get("panic", False)),
            vol_kill_threshold=_safe_opt_float(telem.get("vol_kill_threshold")),
            portfolio_kill_threshold=_safe_opt_float(telem.get("portfolio_kill_threshold")),
        )

    # -----------------------------------------------------
    # EXPOSURE BLOCK
    # -----------------------------------------------------
    def _build_exposure_block(self) -> ExposureBlock:
        """
        Builds exposure summary for the symbol and full portfolio.

        Orchestrator owns:
          - exposure_model
          - portfolio_exposure_usd
        """
        expo_model = getattr(self.orchestrator, "exposure_model", None)

        if expo_model is None:
            return ExposureBlock(
                symbol_exposure_usd=0.0,
                portfolio_exposure_usd=0.0,
                exposure_ratio=0.0,
                exposure_breakdown=[],
            )

        symbol_expo = float(expo_model.symbol_exposure_usd.get(self.symbol, 0.0))
        portfolio_expo = float(expo_model.portfolio_exposure_usd)

        # Pie chart breakdown: one slice per symbol
        breakdown: List[ExposureSlice] = []
        for sym, usd in expo_model.symbol_exposure_usd.items():
            breakdown.append(ExposureSlice(symbol=sym, usd=float(usd)))

        ratio = 0.0
        if portfolio_expo > 0:
            ratio = symbol_expo / portfolio_expo

        return ExposureBlock(
            symbol_exposure_usd=symbol_expo,
            portfolio_exposure_usd=portfolio_expo,
            exposure_ratio=ratio,
            exposure_breakdown=breakdown,
        )

    # -----------------------------------------------------
    # STATE BLOCK (regime + sizing)
    # -----------------------------------------------------
    def _build_state_block(self) -> RiskState:
        """
        Builds the risk state using:
          - orchestrator.status() for last_regime and sizing_state
          - risk_engine panic state
        """
        state = self.orchestrator.status().get(self.symbol, {})

        current_regime = state.get("last_regime", "unknown")
        sizing_state = state.get("sizing_state", "normal")

        panic = False
        telem = getattr(self.risk_engine, "risk_telemetry", None)
        if telem:
            panic = bool(telem.get("panic", False))

        # risk_mode: interpret panic
        if panic:
            risk_mode = "panic"
        else:
            risk_mode = "normal"

        return RiskState(
            current_regime=current_regime,
            sizing_state=sizing_state,
            risk_mode=risk_mode,
        )

    # -----------------------------------------------------
    # POSITION BLOCK
    # -----------------------------------------------------
    def _build_position_block(self) -> PositionBlock:
        """
        Builds current position snapshot:
          - size
          - USD value
          - entry price
          - unrealized PnL (if available)
        """
        pos = getattr(self.engine, "position", None)
        if pos is None:
            return PositionBlock(
                size=0.0,
                usd_value=0.0,
                entry_price=None,
                unrealized_pnl=None,
            )

        size = float(pos.size)
        entry = _safe_opt_float(getattr(pos, "entry_price", None))

        # Engine may provide a method for unrealized pnl; fallback to calculation
        unreal = None
        try:
            if hasattr(self.engine, "get_unrealized_pnl"):
                unreal = float(self.engine.get_unrealized_pnl())
            else:
                if entry is not None:
                    last = float(self.engine.last_price or entry)
                    unreal = (last - entry) * size
        except Exception:
            unreal = None

        # USD notional: pos.size * last price
        try:
            last = float(self.engine.last_price or 0.0)
            usd_value = last * size
        except Exception:
            usd_value = 0.0

        return PositionBlock(
            size=size,
            usd_value=float(usd_value),
            entry_price=entry,
            unrealized_pnl=_safe_opt_float(unreal),
        )


# ---------------------------------------------------------
# Safe numeric helpers
# ---------------------------------------------------------
def _safe_opt_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None

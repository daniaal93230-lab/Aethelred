from __future__ import annotations

import datetime
from typing import List

from api.models.multisymbol_dashboard import (
    MultiSymbolDashboard,
    PortfolioDashboard,
    SymbolDashboardRow,
    InsightMini,
    RiskMini,
    OpsMini,
)

from api.services.insight_dashboard_builder import InsightDashboardBuilder
from api.services.risk_dashboard_builder import RiskDashboardBuilder


class MultiSymbolDashboardBuilder:
    """
    Aggregates all symbol-level dashboards into a unified
    MultiSymbolDashboard snapshot.

    Pulls from:
      - insight_engines[symbol]
      - risk_engines[symbol]
      - engines[symbol]
      - orchestrator (for health + exposure + regime)
    """

    def __init__(self, services):
        """
        services: app.state.services
        Expected attributes:
            - insight_engines
            - risk_engines
            - engines
            - multi_orch
        """
        self.services = services
        self.insight_engines = getattr(services, "insight_engines", {})
        self.risk_engines = getattr(services, "risk_engines", {})
        self.engines = getattr(services, "engines", {})
        self.orchestrator = getattr(services, "multi_orch", None)

    # -----------------------------------------------------
    # Entry point
    # -----------------------------------------------------
    def build(self) -> MultiSymbolDashboard:
        timestamp = datetime.datetime.utcnow().isoformat()

        symbols = sorted(list(self.engines.keys()))
        rows: List[SymbolDashboardRow] = []

        # Portfolio accumulators
        portfolio_volatility = 0.0
        portfolio_exposure = 0.0
        portfolio_alerts: List[str] = []

        expo_model = getattr(self.orchestrator, "exposure_model", None)
        if expo_model:
            try:
                portfolio_volatility = float(getattr(expo_model, "portfolio_volatility", 0.0))
            except Exception:
                portfolio_volatility = 0.0

            try:
                portfolio_exposure = float(getattr(expo_model, "portfolio_exposure_usd", 0.0))
            except Exception:
                portfolio_exposure = 0.0

        # Build each symbol row
        for symbol in symbols:
            rows.append(self._build_symbol_row(symbol, portfolio_alerts))

        portfolio = PortfolioDashboard(
            portfolio_volatility=portfolio_volatility,
            portfolio_exposure_usd=portfolio_exposure,
            symbols_active=len(symbols),
            alerts=portfolio_alerts,
        )

        return MultiSymbolDashboard(
            timestamp=timestamp,
            portfolio=portfolio,
            symbols=rows,
        )

    # -----------------------------------------------------
    # Per-symbol row builder
    # -----------------------------------------------------
    def _build_symbol_row(self, symbol: str, portfolio_alerts: List[str]) -> SymbolDashboardRow:
        insight = self._build_insight_mini(symbol)
        risk = self._build_risk_mini(symbol)
        ops = self._build_ops_mini(symbol)

        # Symbol-level alert logic (expandable in future steps)
        alerts = []
        if risk.panic:
            alerts.append("panic")
            if "panic" not in portfolio_alerts:
                portfolio_alerts.append("panic")

        if risk.sizing_state == "scaled":
            alerts.append("scaled")

        if insight.active_regime:
            alerts.append(f"regime_{insight.active_regime}")

        return SymbolDashboardRow(
            symbol=symbol,
            insight=insight,
            risk=risk,
            ops=ops,
            alerts=alerts,
        )

    # -----------------------------------------------------
    # InsightMini builder
    # -----------------------------------------------------
    def _build_insight_mini(self, symbol: str) -> InsightMini:
        insight_engine = self.insight_engines.get(symbol)
        orchestrator = self.orchestrator
        history = getattr(self.services, "telemetry_history", None)

        if insight_engine is None or orchestrator is None or history is None:
            return InsightMini()

        # Build using InsightDashboardBuilder (cached)
        builder = InsightDashboardBuilder(
            insight_engine=insight_engine,
            orchestrator=orchestrator,
            history=history,
            symbol=symbol,
        )
        full = builder.build()

        # Extract latest rolling metrics
        rolling = full.performance.get("rolling", {})
        sharpe = _latest_value(rolling.get("sharpe"))
        sortino = _latest_value(rolling.get("sortino"))
        calmar = _latest_value(rolling.get("calmar"))

        return InsightMini(
            sharpe=sharpe,
            sortino=sortino,
            calmar=calmar,
            daily_pnl=full.kpis.daily_pnl,
            active_regime=full.kpis.active_regime,
            top_strategy=full.kpis.top_strategy,
        )

    # -----------------------------------------------------
    # RiskMini builder
    # -----------------------------------------------------
    def _build_risk_mini(self, symbol: str) -> RiskMini:
        risk_engine = self.risk_engines.get(symbol)
        engine = self.engines.get(symbol)
        orchestrator = self.orchestrator

        if risk_engine is None or engine is None or orchestrator is None:
            return RiskMini(
                volatility=0.0,
                exposure_usd=0.0,
                sizing_state="unknown",
                panic=False,
            )

        builder = RiskDashboardBuilder(
            symbol=symbol,
            risk_engine=risk_engine,
            orchestrator=orchestrator,
            engine=engine,
        )

        full = builder.build()

        # Extract compact fields
        exposure_usd = float(full.exposure.symbol_exposure_usd)

        return RiskMini(
            volatility=float(full.risk.volatility),
            exposure_usd=exposure_usd,
            sizing_state=full.state.sizing_state,
            panic=full.risk.panic,
        )

    # -----------------------------------------------------
    # OpsMini builder
    # -----------------------------------------------------
    def _build_ops_mini(self, symbol: str) -> OpsMini:
        orch = self.orchestrator

        if orch is None:
            return OpsMini(
                status="unknown",
                last_cycle_ms=None,
                stalled=False,
                last_error=None,
            )

        status_map = orch.status()
        row = status_map.get(symbol, {})

        return OpsMini(
            status=row.get("status", "unknown"),
            last_cycle_ms=row.get("last_cycle_ms"),
            stalled=bool(row.get("stalled", False)),
            last_error=row.get("last_error"),
        )


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------
def _latest_value(series):
    """
    Extracts the latest .value from a list of dicts:
    [ {"ts": ..., "value": ...}, ... ]
    """
    if not series:
        return None
    try:
        last = series[-1]
        return float(last.get("value"))
    except Exception:
        return None

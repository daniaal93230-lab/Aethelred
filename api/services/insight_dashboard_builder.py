from __future__ import annotations

import datetime
import math
from api.services.cache import TTLCache
from typing import Optional, List

from api.models.insight_dashboard import (
    InsightDashboard,
    RollingPoint,
    RollingPerformance,
    StrategyMAEMFE,
    KPITiles,
    TradeRecord,
)


# ---------------------------------------------------------
# Builder service for InsightDashboard
# ---------------------------------------------------------
class InsightDashboardBuilder:
    """
    Pure builder that aggregates:
      - insight engine (MAE/MFE, KPIs, trade stats)
      - orchestrator regime/strategy info
      - telemetry history (rolling equity, sharpe, sortino, calmar)

    This class produces a valid InsightDashboard model and
    does not touch any external routes directly.
    """

    # Global cache for all symbols (2-second default TTL)
    _cache = TTLCache(ttl_seconds=2.0)

    def __init__(
        self,
        insight_engine,
        orchestrator,
        history,
        symbol: str,
    ):
        self.insight_engine = insight_engine
        self.orchestrator = orchestrator
        self.history = history
        self.symbol = symbol

    # -----------------------------------------------------
    # Public entry point
    # -----------------------------------------------------
    def build(self) -> InsightDashboard:
        """
        Build a complete InsightDashboard snapshot.
        """
        # 1. Cache lookup (per-symbol)
        cached = self._cache.get(self.symbol)
        if cached is not None:
            return cached

        timestamp = datetime.datetime.utcnow().isoformat()

        performance = self._build_performance_block()
        mae_mfe = self._build_mae_mfe_table()
        kpis = self._build_kpis()
        trades = self._build_recent_trades()

        # Normalise all time-series and tables for frontend safety
        self._normalise(performance, mae_mfe, trades)

        dashboard = InsightDashboard(
            symbol=self.symbol,
            timestamp=timestamp,
            performance={"rolling": performance.model_dump()},
            strategy_mae_mfe=mae_mfe,
            kpis=kpis,
            recent_trades=trades,
        )

        # 2. Cache store and return
        try:
            self._cache.set(self.symbol, dashboard)
        except Exception:
            # non-fatal: cache failure shouldn't break response
            pass

        return dashboard

    # -----------------------------------------------------
    # Rolling performance metrics
    # -----------------------------------------------------
    def _build_performance_block(self) -> RollingPerformance:
        """
        Build rolling Sharpe, Sortino, Calmar, and equity curve
        directly from telemetry history.
        """
        # history returns a deque of per-tick snapshots
        snapshots = self.history.get_symbol_history(self.symbol)

        sharpe_points: List[RollingPoint] = []
        sortino_points: List[RollingPoint] = []
        calmar_points: List[RollingPoint] = []
        equity_points: List[RollingPoint] = []

        for snap in snapshots:
            ts = snap.get("ts")
            perf = snap.get("performance", {})

            if ts is None:
                continue

            if "sharpe" in perf:
                sharpe_points.append(RollingPoint(ts=ts, value=float(perf["sharpe"])))

            if "sortino" in perf:
                sortino_points.append(RollingPoint(ts=ts, value=float(perf["sortino"])))

            if "calmar" in perf:
                calmar_points.append(RollingPoint(ts=ts, value=float(perf["calmar"])))

            if "equity" in perf:
                equity_points.append(RollingPoint(ts=ts, value=float(perf["equity"])))

        # Window size based on insight engine parameters (fallback)
        window_trades = getattr(self.insight_engine, "rolling_window", 200)

        return RollingPerformance(
            window_trades=window_trades,
            sharpe=sharpe_points,
            sortino=sortino_points,
            calmar=calmar_points,
            equity_curve=equity_points,
        )

    # -----------------------------------------------------
    # MAE/MFE per-strategy table
    # -----------------------------------------------------
    def _build_mae_mfe_table(self) -> List[StrategyMAEMFE]:
        """
        Build per-strategy aggregated MAE/MFE stats.
        """
        results = []
        stats = self.insight_engine.get_strategy_stats()

        for name, row in stats.items():
            results.append(
                StrategyMAEMFE(
                    strategy=name,
                    count=row.get("count", 0),
                    avg_mae=float(row.get("avg_mae", 0)),
                    avg_mfe=float(row.get("avg_mfe", 0)),
                    win_rate=float(row.get("win_rate", 0)),
                    median_hold_seconds=int(row.get("median_hold_seconds", 0)),
                )
            )

        return results

    # -----------------------------------------------------
    # KPI tiles block
    # -----------------------------------------------------
    def _build_kpis(self) -> KPITiles:
        """
        Build KPI tiles using daily KPI snapshot + orchestrator state.
        """
        daily = self.insight_engine.get_daily_kpi()

        regime = None
        top_strategy = None

        # Orchestrator may provide last regime and best strategy
        orch_state = self.orchestrator.status().get(self.symbol, {})
        if "last_regime" in orch_state:
            regime = orch_state["last_regime"]

        if "best_strategy" in orch_state:
            top_strategy = orch_state["best_strategy"]

        return KPITiles(
            daily_pnl=float(daily.get("daily_pnl", 0)),
            daily_return_pct=float(daily.get("daily_return_pct", 0)),
            max_drawdown_pct=float(daily.get("max_drawdown_pct", 0)),
            trade_count=int(daily.get("trade_count", 0)),
            active_regime=regime or daily.get("active_regime", "unknown"),
            top_strategy=top_strategy or daily.get("top_strategy") or None,
        )

    # -----------------------------------------------------
    # Recent trades (closed)
    # -----------------------------------------------------
    def _build_recent_trades(self) -> List[TradeRecord]:
        """
        Build recent closed trades from the insight engine.
        """
        trades = self.insight_engine.get_recent_trades(self.symbol)
        result: List[TradeRecord] = []

        for t in trades:
            result.append(
                TradeRecord(
                    trade_id=t.get("id"),
                    side=t.get("side"),
                    strategy=t.get("strategy"),
                    entry_ts=int(t.get("entry_ts")),
                    exit_ts=_opt_int(t.get("exit_ts")),
                    entry_price=float(t.get("entry_price")),
                    exit_price=_opt_float(t.get("exit_price")),
                    pnl=_opt_float(t.get("pnl")),
                    mfe=_opt_float(t.get("mfe")),
                    mae=_opt_float(t.get("mae")),
                    holding_seconds=_opt_int(t.get("holding_seconds")),
                )
            )

        return result


# ---------------------------------------------------------
# Safe optional converters
# ---------------------------------------------------------
def _opt_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _opt_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None

    # ---------------------------------------------------------
    # Normalisation Layer (7.A-5)
    # Ensures stable, frontend-safe output for all Insight dashboards
    # ---------------------------------------------------------
    def _normalise(
        self,
        performance: RollingPerformance,
        mae_mfe: List[StrategyMAEMFE],
        trades: List[TradeRecord],
    ) -> None:
        """
        Post-processing pass:
         - Sorts time-series ascending
         - Removes NaN/None values
         - Rounds floats to 8 decimals
         - Ensures no missing fields
         - Ensures stable ordering of strategy MAE/MFE tables
        """
        # --- time-series sorting ---
        self._sort_series(performance.sharpe)
        self._sort_series(performance.sortino)
        self._sort_series(performance.calmar)
        self._sort_series(performance.equity_curve)

        # --- clean series ---
        performance.sharpe[:] = self._clean_numeric_series(performance.sharpe)
        performance.sortino[:] = self._clean_numeric_series(performance.sortino)
        performance.calmar[:] = self._clean_numeric_series(performance.calmar)
        performance.equity_curve[:] = self._clean_numeric_series(performance.equity_curve)

        # --- clean MAE/MFE ---
        mae_mfe.sort(key=lambda x: x.strategy)

        for entry in mae_mfe:
            entry.avg_mae = self._safe_num(entry.avg_mae)
            entry.avg_mfe = self._safe_num(entry.avg_mfe)
            entry.win_rate = self._safe_num(entry.win_rate)

        # --- trade ordering (newest last) ---
        trades.sort(key=lambda t: t.entry_ts)

        for t in trades:
            # None or nan safe conversions
            t.pnl = self._safe_opt_num(t.pnl)
            t.mfe = self._safe_opt_num(t.mfe)
            t.mae = self._safe_opt_num(t.mae)

    # -----------------------------------------------------
    # Helpers
    # -----------------------------------------------------
    @staticmethod
    def _sort_series(points: List[RollingPoint]) -> None:
        points.sort(key=lambda p: p.ts)

    @staticmethod
    def _clean_numeric_series(points: List[RollingPoint]) -> List[RollingPoint]:
        cleaned = []
        for p in points:
            if p.value is None or math.isnan(p.value):
                continue
            cleaned.append(RollingPoint(ts=p.ts, value=round(float(p.value), 8)))
        return cleaned

    @staticmethod
    def _safe_num(v: float) -> float:
        try:
            if v is None or math.isnan(v):
                return 0.0
            return round(float(v), 8)
        except Exception:
            return 0.0

    @staticmethod
    def _safe_opt_num(v: Optional[float]) -> Optional[float]:
        if v is None:
            return None
        try:
            if math.isnan(v):
                return None
            return round(float(v), 8)
        except Exception:
            return None

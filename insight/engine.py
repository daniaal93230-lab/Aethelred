"""
Insight Engine V1 (Phase 6.E Batch 6.A)

Standalone subsystem for analytics. This module is isolated and not
automatically attached to the ExecutionEngine; integration happens in
Phase 6.E-2 to preserve test isolation.

Implements:
  - Trade-level MAE/MFE tracking
  - Per-strategy aggregation
  - Per-regime aggregation
  - JSON-safe snapshot API
"""

from __future__ import annotations

from decimal import Decimal
from dataclasses import dataclass
from typing import Dict, Any, Optional, Deque
import os
import csv
from datetime import datetime
from collections import deque

from .utils import compute_mae_mfe, decimal_or_zero


@dataclass
class TradeMAE_MFE:
    mae: Decimal
    mfe: Decimal
    entry_price: Decimal
    exit_price: Optional[Decimal]
    regime: str
    strategy: str


class InsightEngine:
    """Core insight engine. Light-weight and test-safe."""

    def __init__(self) -> None:
        # trade_id -> TradeMAE_MFE
        self.trades: Dict[str, TradeMAE_MFE] = {}

        # Aggregations
        self.strategy_stats: Dict[str, Dict[str, Decimal]] = {}
        self.regime_stats: Dict[str, Dict[str, Decimal]] = {}
        # ------------------------------------------------------------
        # Phase 6.E-3 — Rolling Metrics (Sharpe, Sortino, Calmar)
        # ------------------------------------------------------------
        self.rolling_returns: Deque[Decimal] = deque(maxlen=100)  # 100-trade window
        self.rolling_equity_peak = Decimal("1")
        self.rolling_equity = Decimal("1")
        self.rolling_metrics = {
            "sharpe": Decimal("0"),
            "sortino": Decimal("0"),
            "calmar": Decimal("0"),
        }

    # -----------------------------
    # Public API
    # -----------------------------
    def record_trade(
        self,
        trade_id: str,
        *,
        entry_price: Any,
        high: Any,
        low: Any,
        exit_price: Optional[Any],
        strategy: str,
        regime: str,
    ) -> None:
        """Record a trade's MAE/MFE and update aggregations.

        Parameters are permissive (any) — converted via decimal_or_zero.
        """
        ep = decimal_or_zero(entry_price)
        hp = decimal_or_zero(high)
        lp = decimal_or_zero(low)
        xp = decimal_or_zero(exit_price) if exit_price is not None else None

        metrics = compute_mae_mfe(ep, hp, lp)

        t = TradeMAE_MFE(
            mae=metrics["mae"],
            mfe=metrics["mfe"],
            entry_price=ep,
            exit_price=xp,
            regime=str(regime),
            strategy=str(strategy),
        )

        self.trades[trade_id] = t

        self._update_strategy_stats(t)
        self._update_regime_stats(t)

        # ------------------------------------------------------------
        # Phase 6.E-3 — Feed rolling returns
        # ------------------------------------------------------------
        try:
            if t.entry_price > 0 and t.exit_price:
                ret = (t.exit_price - t.entry_price) / t.entry_price
                self._update_rolling_metrics(ret)
        except Exception:
            pass

    # -----------------------------
    # Aggregation helpers
    # -----------------------------
    def _update_strategy_stats(self, t: TradeMAE_MFE) -> None:
        b = self.strategy_stats.setdefault(
            t.strategy, {"count": Decimal("0"), "sum_mae": Decimal("0"), "sum_mfe": Decimal("0")}
        )
        b["count"] += Decimal("1")
        b["sum_mae"] += t.mae
        b["sum_mfe"] += t.mfe

    def _update_regime_stats(self, t: TradeMAE_MFE) -> None:
        b = self.regime_stats.setdefault(
            t.regime, {"count": Decimal("0"), "sum_mae": Decimal("0"), "sum_mfe": Decimal("0")}
        )
        b["count"] += Decimal("1")
        b["sum_mae"] += t.mae
        b["sum_mfe"] += t.mfe

    # ------------------------------------------------------------------
    # Phase 6.E-3 — Rolling Metric Engine
    # ------------------------------------------------------------------
    def _update_rolling_metrics(self, ret: Decimal) -> None:
        """Update rolling return window and recompute metrics."""
        self.rolling_returns.append(ret)

        # rolling equity curve
        try:
            self.rolling_equity *= Decimal("1") + ret
        except Exception:
            pass
        if self.rolling_equity > self.rolling_equity_peak:
            self.rolling_equity_peak = self.rolling_equity

        # compute all metrics
        self.rolling_metrics["sharpe"] = self._compute_sharpe()
        self.rolling_metrics["sortino"] = self._compute_sortino()
        self.rolling_metrics["calmar"] = self._compute_calmar()

    def _compute_sharpe(self) -> Decimal:
        rs = list(self.rolling_returns)
        if len(rs) < 2:
            return Decimal("0")
        mean = sum(rs) / Decimal(len(rs))
        var = sum((r - mean) ** 2 for r in rs) / Decimal(len(rs))
        sd = var.sqrt()
        if sd == 0:
            return Decimal("0")
        return mean / sd

    def _compute_sortino(self) -> Decimal:
        rs = list(self.rolling_returns)
        if len(rs) < 2:
            return Decimal("0")
        neg = [r for r in rs if r < 0]
        if not neg:
            return Decimal("0")
        mean = sum(rs) / Decimal(len(rs))
        var = sum((r - mean) ** 2 for r in neg) / Decimal(len(neg))
        sd = var.sqrt()
        if sd == 0:
            return Decimal("0")
        return mean / sd

    def _compute_calmar(self) -> Decimal:
        """Return-based Calmar approximation over rolling equity."""
        try:
            dd = (self.rolling_equity_peak - self.rolling_equity) / self.rolling_equity_peak
            if dd <= 0:
                return Decimal("0")
            # annualization is not applied here — rolling window approx
            ret_total = self.rolling_equity - Decimal("1")
            return ret_total / dd
        except Exception:
            return Decimal("0")

    # -----------------------------
    # Snapshot
    # -----------------------------
    def snapshot(self) -> Dict[str, Any]:
        """Return a JSON-serializable snapshot of trades and aggregations."""

        def _clean(v):
            if isinstance(v, Decimal):
                return float(v)
            if isinstance(v, dict):
                return {k: _clean(x) for k, x in v.items()}
            if isinstance(v, TradeMAE_MFE):
                return {
                    "mae": float(v.mae),
                    "mfe": float(v.mfe),
                    "entry_price": float(v.entry_price),
                    "exit_price": float(v.exit_price) if v.exit_price is not None else None,
                    "regime": v.regime,
                    "strategy": v.strategy,
                }
            return v

        return {
            "trades": {tid: _clean(t) for tid, t in self.trades.items()},
            "strategy_stats": _clean(self.strategy_stats),
            "regime_stats": _clean(self.regime_stats),
            "rolling_metrics": {
                "sharpe": float(self.rolling_metrics["sharpe"]),
                "sortino": float(self.rolling_metrics["sortino"]),
                "calmar": float(self.rolling_metrics["calmar"]),
            },
        }

        # ------------------------------------------------------------------
        # Phase 6.E-4 — Daily KPI Export
        # ------------------------------------------------------------------
        def export_daily_kpi(self, base_path: str = "insight/kpi") -> str:
            """
            Writes a daily KPI CSV:
                insight/kpi/YYYY-MM-DD.csv
            Returns full filepath.
            """
            try:
                # Ensure folder exists
                if not os.path.exists(base_path):
                    os.makedirs(base_path, exist_ok=True)

                today = datetime.utcnow().strftime("%Y-%m-%d")
                filepath = os.path.join(base_path, f"{today}.csv")

                snap = self.snapshot()

                # Flatten metrics for CSV
                rows = []

                # Rolling metrics summary
                rows.append(
                    {
                        "metric": "rolling_sharpe",
                        "value": snap["rolling_metrics"]["sharpe"],
                    }
                )
                rows.append(
                    {
                        "metric": "rolling_sortino",
                        "value": snap["rolling_metrics"]["sortino"],
                    }
                )
                rows.append(
                    {
                        "metric": "rolling_calmar",
                        "value": snap["rolling_metrics"]["calmar"],
                    }
                )

                # Strategy aggregates
                for strat, stats in snap["strategy_stats"].items():
                    rows.append(
                        {
                            "metric": f"strategy_{strat}_count",
                            "value": float(stats.get("count", 0)),
                        }
                    )
                    rows.append(
                        {
                            "metric": f"strategy_{strat}_avg_mae",
                            "value": float(stats.get("sum_mae", 0) / stats["count"]) if stats.get("count") else 0,
                        }
                    )
                    rows.append(
                        {
                            "metric": f"strategy_{strat}_avg_mfe",
                            "value": float(stats.get("sum_mfe", 0) / stats["count"]) if stats.get("count") else 0,
                        }
                    )

                # Regime aggregates
                for reg, stats in snap["regime_stats"].items():
                    rows.append(
                        {
                            "metric": f"regime_{reg}_count",
                            "value": float(stats.get("count", 0)),
                        }
                    )
                    rows.append(
                        {
                            "metric": f"regime_{reg}_avg_mae",
                            "value": float(stats.get("sum_mae", 0) / stats["count"]) if stats.get("count") else 0,
                        }
                    )
                    rows.append(
                        {
                            "metric": f"regime_{reg}_avg_mfe",
                            "value": float(stats.get("sum_mfe", 0) / stats["count"]) if stats.get("count") else 0,
                        }
                    )

                # Write CSV
                with open(filepath, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=["metric", "value"])
                    writer.writeheader()
                    for r in rows:
                        writer.writerow(r)

                return filepath

            except Exception as e:
                return f"ERROR: {e}"

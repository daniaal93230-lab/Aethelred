from __future__ import annotations

import asyncio
import time
import uuid
from utils.logger import logger, log_extra
from decimal import Decimal
from typing import Dict, Any

from core.execution_engine import ExecutionEngine
from core.telemetry_bus_v2 import TelemetryBusV2
from core.telemetry_history_v2 import TelemetryHistoryV2
from ops.notifier import get_notifier


class OrchestratorV2:
    """
    Orchestrator V2 (Async)
    -----------------------

    Drives ExecutionEngine instances in a continuous asynchronous loop.

    Responsibilities:
      - Manage multiple engines (multi-symbol)
      - Trigger engine.run_once() at fixed intervals
      - Collect equity + PnL states
      - Propagate global risk-off
      - Enforce kill-switches
      - Expose snapshots for API/telemetry

    Paper-mode only for now (Phase 5 enables live routing).
    """

    def __init__(
        self,
        symbols=None,
        telemetry_bus: TelemetryBusV2 | None = None,
        history: TelemetryHistoryV2 | None = None,
    ):
        self.symbols = symbols or ["BTC/USDT"]

        # Engines keyed by symbol
        self.engines: Dict[str, ExecutionEngine] = {
            sym: ExecutionEngine() for sym in self.symbols
        }

        # Telemetry bus (optional, can be wired by API layer)
        self.telemetry_bus = telemetry_bus

        # Rolling history buffer
        self.history: TelemetryHistoryV2 = history or TelemetryHistoryV2()

        # --- Global orchestrator state ---
        self.global_risk_off: bool = False
        self.global_killed: bool = False

        # Per-symbol soft/hard kill flags
        self.symbol_kill: Dict[str, bool] = {sym: False for sym in self.symbols}
        self.symbol_risk_off: Dict[str, bool] = {sym: False for sym in self.symbols}

        # Telemetry cache: per-symbol snapshots and portfolio snapshot
        self.last_snapshots: Dict[str, Any] = {}
        self.portfolio_snapshot: Dict[str, Any] = {
            "portfolio_equity": 10000 * len(self.symbols),
            "total_realized_pnl": 0.0,
            "total_unrealized_pnl": 0.0,
            "timestamp": 0,
        }

        # track max portfolio equity for drawdown calculation
        self._max_portfolio_equity = Decimal("0")
        # per-symbol cycle timing and kill flags
        self._last_cycle_ms: Dict[str, float] = {sym: 0.0 for sym in self.symbols}
        self.last_cycle_ts: Dict[str, float] = {sym: 0.0 for sym in self.symbols}
        self.kill_flags: Dict[str, Dict[str, bool]] = {sym: {"risk_off": False, "drawdown": False} for sym in self.symbols}

        # alerting guard to avoid repeated hard-drawdown notifications
        self._hard_dd_alerted = False

    # ----------------------------------------------------------------------
    # Kill Switches
    # ----------------------------------------------------------------------
    def kill_all(self) -> None:
        """Hard kill for all engines."""
        self.global_killed = True
        for eng in self.engines.values():
            eng.global_risk_off = True

    def risk_off_all(self) -> None:
        """Soft kill: no new positions."""
        self.global_risk_off = True
        for eng in self.engines.values():
            eng.global_risk_off = True

    def risk_on_all(self) -> None:
        """Re-enable all engines."""
        self.global_risk_off = False
        for eng in self.engines.values():
            eng.global_risk_off = False

    # ----------------------------------------------------------------------
    # Async Engine Loop
    # ----------------------------------------------------------------------
    async def run_symbol(self, symbol: str, interval: float = 2.0):
        """Runs one symbol's engine in a loop."""
        eng = self.engines[symbol]

        while not self.global_killed:
            # If symbol is hard-killed → skip but do not exit process
            if self.symbol_kill.get(symbol, False):
                await asyncio.sleep(interval)
                continue

            cid = uuid.uuid4().hex[:12]
            ts0 = time.perf_counter()

            try:
                # enforce global risk-off
                if self.global_risk_off:
                    eng.global_risk_off = True

                # enforce per-symbol risk-off
                if self.symbol_risk_off.get(symbol, False):
                    eng.risk_off = True

                # Update engine equity from portfolio snapshot (future use, Phase 5)
                # For now each engine maintains own equity via executor.
                # Provided as placeholder for global allocation logic.

                # pass correlation id into engine so internal logs/alerts are traceable
                try:
                    eng.run_once(is_mock=True, cid=cid)
                except TypeError:
                    # older engines may not accept cid; fallback
                    eng.run_once(is_mock=True)

                snap = eng.snapshot()
                # include risk_v3 telemetry snapshot when available (non-invasive)
                try:
                    try:
                        risk_snapshot = eng.risk_v3.telemetry_snapshot() if getattr(eng, "risk_v3", None) is not None else None
                    except Exception:
                        risk_snapshot = None
                    if risk_snapshot is not None:
                        snap["risk_v3"] = risk_snapshot
                    else:
                        snap["risk_v3"] = {"status": "unavailable"}
                except Exception:
                    try:
                        snap["risk_v3"] = {"status": "unavailable"}
                    except Exception:
                        pass

                self.last_snapshots[symbol] = snap

                # Update portfolio snapshot (pass cid for traceability)
                try:
                    self._update_portfolio_snapshot(cid=cid)
                except TypeError:
                    # fallback for older signature
                    self._update_portfolio_snapshot()

                # Store history
                try:
                    self.history.push_symbol(symbol, snap)
                    self.history.push_portfolio(self.portfolio_snapshot)
                except Exception:
                    # history is best-effort and must not break loop
                    pass

                # Telemetry publish
                if self.telemetry_bus is not None:
                    try:
                        self.telemetry_bus.publish(f"symbol.{symbol}", snap)
                        self.telemetry_bus.publish("portfolio", self.portfolio_snapshot)
                    except Exception:
                        # Telemetry must never break the loop
                        pass

            except Exception:
                # metric: engine error count (best-effort)
                try:
                    try:
                        from api.routes.metrics import aet_engine_errors_total
                    except Exception:
                        aet_engine_errors_total = None
                    if aet_engine_errors_total is not None:
                        aet_engine_errors_total.labels(symbol=symbol).inc()
                except Exception:
                    pass

                # notify ops asynchronously (best-effort)
                try:
                    get_notifier().send("engine_error", symbol=symbol, msg="Engine loop exception", cid=cid)
                except Exception:
                    pass

                # never break orchestrator loop
                pass
            ts1 = time.perf_counter()
            ms = (ts1 - ts0) * 1000
            try:
                self._last_cycle_ms[symbol] = ms
                self.last_cycle_ts[symbol] = time.time()
            except Exception:
                pass

            # slow-cycle detection and structured cycle log
            try:
                max_ms = getattr(getattr(self, "engine", None), "cycle_delay", None)
                # if orchestrator doesn't have engine.cycle_delay, try per-engine attribute
                if max_ms is None:
                    max_ms = getattr(eng, "cycle_delay", None)
                if max_ms is not None:
                    max_ms = float(max_ms) * 1000 * 1.5
                    if ms > max_ms:
                        try:
                            logger.warning(
                                f"slow cycle for {symbol}",
                                **log_extra(symbol=symbol, cid=cid, duration_ms=ms),
                            )
                        except Exception:
                            pass
            except Exception:
                pass

            try:
                logger.info(
                    "cycle complete",
                    **log_extra(symbol=symbol, cid=cid, duration_ms=ms),
                )
            except Exception:
                pass

            # increment orchestrator cycle counter (best-effort)
            try:
                try:
                    from api.routes.metrics import aet_orch_cycles_total
                except Exception:
                    aet_orch_cycles_total = None
                if aet_orch_cycles_total is not None:
                    try:
                        # use symbol label if supported
                        if hasattr(aet_orch_cycles_total, "labels"):
                            aet_orch_cycles_total.labels(symbol=symbol).inc()
                        else:
                            aet_orch_cycles_total.inc()
                    except Exception:
                        pass
            except Exception:
                pass

            # update per-symbol kill_flags based on engine state
            try:
                self.kill_flags[symbol]["risk_off"] = bool(getattr(self.engines[symbol], "risk_off", False) or getattr(self.engines[symbol], "global_risk_off", False))
                cur_dd = getattr(self.engines[symbol], "current_drawdown", None)
                if cur_dd is not None:
                    try:
                        self.kill_flags[symbol]["drawdown"] = float(cur_dd) >= float(getattr(self.engines[symbol], "hard_dd_threshold", 0.25))
                    except Exception:
                        pass
            except Exception:
                pass

            elapsed = (ts1 - ts0)
            wait = max(0.0, interval - elapsed)
            await asyncio.sleep(wait)

    # ----------------------------------------------------------------------
    # Multi-Symbol Launcher
    # ----------------------------------------------------------------------
    async def run_all(self, interval: float = 2.0):
        """Run all symbols concurrently."""
        tasks = [
            asyncio.create_task(self.run_symbol(sym, interval))
            for sym in self.symbols
        ]
        await asyncio.gather(*tasks)

    # ----------------------------------------------------------------------
    # Snapshot API
    # ----------------------------------------------------------------------
    def snapshot(self) -> Dict[str, Any]:
        """Return last known state for all symbols."""
        return {
            "symbols": self.last_snapshots,
            "portfolio": self.portfolio_snapshot,
        }

    # ----------------------------------------------------------------------
    # Portfolio State Aggregation
    # ----------------------------------------------------------------------
    def _update_portfolio_snapshot(self, cid: str | None = None) -> None:
        """Compute portfolio-level PnL and equity."""
        total_realized = Decimal("0")
        total_unrealized = Decimal("0")
        total_equity = Decimal("0")

        for sym, snap in self.last_snapshots.items():
            exec_section = snap.get("execution", {})
            total_realized += Decimal(str(exec_section.get("realized_pnl", "0")))
            total_unrealized += Decimal(str(exec_section.get("unrealized_pnl", "0")))
            total_equity += Decimal(str(exec_section.get("equity_now", "10000")))

        self.portfolio_snapshot = {
            "portfolio_equity": float(total_equity),
            "total_realized_pnl": float(total_realized),
            "total_unrealized_pnl": float(total_unrealized),
            "timestamp": time.time(),
        }

        # compute drawdown against historical max and publish gauge
        try:
            if total_equity > self._max_portfolio_equity:
                self._max_portfolio_equity = total_equity
            dd = Decimal("0")
            if self._max_portfolio_equity > 0:
                dd = (self._max_portfolio_equity - total_equity) / self._max_portfolio_equity
            # set prometheus drawdown gauge (best-effort)
            try:
                try:
                    from api.routes.metrics import aet_drawdown_pct
                except Exception:
                    aet_drawdown_pct = None
                if aet_drawdown_pct is not None:
                    try:
                        aet_drawdown_pct.set(float(dd))
                    except Exception:
                        pass
            except Exception:
                pass

            # alert on hard drawdown threshold once
            try:
                HARD_DD_THRESHOLD = getattr(self, "hard_dd_threshold", 0.25)
                if dd >= Decimal(str(HARD_DD_THRESHOLD)) and not getattr(self, "_hard_dd_alerted", False):
                    try:
                        get_notifier().send("hard_drawdown", msg="Portfolio hard drawdown reached", drawdown=float(dd), cid=cid)
                    except Exception:
                        pass
                    self._hard_dd_alerted = True
                # reset alert if drawdown improves significantly
                if dd < Decimal(str(HARD_DD_THRESHOLD)) / 2 and getattr(self, "_hard_dd_alerted", False):
                    self._hard_dd_alerted = False
            except Exception:
                pass
        except Exception:
            pass

    # ----------------------------------------------------------------------
    # Symbol-level Kill Switches
    # ----------------------------------------------------------------------
    def kill_symbol(self, symbol: str) -> None:
        """Hard kill for individual symbol."""
        if symbol in self.symbols:
            self.symbol_kill[symbol] = True
            self.engines[symbol].global_risk_off = True

    def risk_off_symbol(self, symbol: str) -> None:
        """Soft kill: no new positions for a symbol."""
        if symbol in self.symbols:
            self.symbol_risk_off[symbol] = True
            self.engines[symbol].risk_off = True

    def risk_on_symbol(self, symbol: str) -> None:
        """Re-enable a symbol."""
        if symbol in self.symbols:
            self.symbol_risk_off[symbol] = False
            self.symbol_kill[symbol] = False
            self.engines[symbol].risk_off = False

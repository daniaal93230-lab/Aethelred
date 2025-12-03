"""
Async Orchestrator (Phase 1)

Responsibilities:
 - run Engine.run_once() forever
 - adaptive cadence:
       trend → 1s
       normal → 3s
       chop → 7s
       panic → 15s
 - process tasks from TaskQueue (train / shutdown)
 - write state to StateStore

Production-grade, test-safe, dependency-injection-ready.
"""

from __future__ import annotations
import asyncio
import traceback
from collections import OrderedDict
import logging
import time
from typing import Optional, Dict, List, Any
from enum import Enum

from api.core.task_queue import Task, TaskQueue
from api.core.state_store import StateStore
from core.runtime_state import kill_is_on
from core.runtime_state import record_event
from datetime import datetime, timezone
from utils.logger import logger
from api.routes.metrics import aet_kill_switch_state, aet_engine_errors_total


# ---- Cadence table ----
CADENCE = {
    "trend": 1.0,
    "normal": 3.0,
    "chop": 7.0,
    "panic": 15.0,
}


class EngineOrchestrator:
    """Per-symbol orchestrator.

    Lightweight orchestrator that runs the provided `engine` in a tight
    async loop. Designed to be instantiated once per symbol and started/stopped
    independently by the application lifecycle.
    """

    def __init__(self, engine: Any, symbol: str) -> None:
        self.engine = engine
        self.symbol = symbol
        self._running = False
        # telemetry
        self._last_cycle_latency: dict[str, int] = {}
        # pause/kill flags (managed by external controller)
        self.is_paused: bool = False
        self.is_killed: bool = False
        # per-symbol risk-off flag (controls new position entry)
        self.risk_off: bool = False
        # state store (shared across app in the original design)
        self.state = StateStore()
        # queue / inflight / task bookkeeping for enqueue_train and shutdown
        self.queue: asyncio.Queue = asyncio.Queue()
        self._inflight: dict = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._shutting_down: bool = False
        self._manager_task: Optional[asyncio.Task] = None

    def pause(self) -> None:
        """Pause the orchestrator; safe to call from engine callbacks."""
        try:
            self.is_paused = True
        except Exception:
            pass

    def set_risk_off(self, value: bool) -> None:
        """
        Per-symbol risk-off setter. Propagates to the engine so the engine
        will suppress new entries for this symbol.
        """
        try:
            self.risk_off = bool(value)
            if hasattr(self, "engine"):
                setattr(self.engine, "risk_off", bool(value))
        except Exception:
            pass

    def attach_pause_callback(self) -> None:
        """Bind engine.pause_callback to this orchestrator's pause method.

        This allows the engine to request a pause (hard drawdown kill-switch)
        without knowing orchestrator internals.
        """
        try:
            setattr(self.engine, "pause_callback", self.pause)
        except Exception:
            pass

    # ------------------------------------------------------------
    # External control API (used by FastAPI or tests)
    # ------------------------------------------------------------

    async def enqueue_train(self, job: str, notes: Optional[str] = None) -> str:
        """Compatibility shim for engine.enqueue_train."""
        # Batch 6D: HARD kill → reject new jobs
        if self._shutting_down or kill_is_on():
            raise RuntimeError("orchestrator shutting down or kill-switch active")

        ticket = f"train-{job}-{int(time.time())}"
        task = Task(
            "train",
            {"job": job, "notes": notes},
            ticket=ticket,
            attempts=0,
            enqueued_ts=time.time(),
        )
        await self.queue.put(task)
        return ticket

    async def shutdown(self):
        """
        Graceful orchestrator shutdown:
          - Block new enqueues
          - Requeue in-flight tasks
          - Insert shutdown signal
        """
        self._shutting_down = True

        # Requeue tasks being processed (increment attempts)
        for tid, meta in list(self._inflight.items()):
            try:
                task = meta["task"]
                task.attempts = int(getattr(task, "attempts", 0)) + 1
                await self.queue.put(task)
            except Exception:
                pass

        await self.queue.put(Task("shutdown", {}, ticket=f"shutdown-{int(time.time())}", attempts=0, enqueued_ts=time.time()))

        # signal local kill and stop running loops
        self.is_killed = True
        self._running = False

        # cancel per-engine tasks
        for t in list(self._tasks.values()):
            try:
                t.cancel()
            except Exception:
                pass
        self._tasks.clear()

        # cancel manager task
        try:
            if self._manager_task is not None:
                self._manager_task.cancel()
        except Exception:
            pass

    # ------------------------------------------------------------
    # Core Loop
    # ------------------------------------------------------------

    async def start(self) -> None:
        """Start the per-symbol loop. This schedules a continuous run until
        `stop()` is called."""
        # Only start if not already running
        if getattr(self, "_task", None) and not self._task.done():
            return

        self._running = True
        loop = asyncio.get_running_loop()

        async def _runner():
            while self._running and not self.is_killed:
                await self._loop_once()
                await asyncio.sleep(0.25)

        # Track task so MultiOrch can monitor it
        self._task = loop.create_task(_runner())

    def stop(self) -> None:
        # Safe stop flag
        self._running = False
        self.is_killed = True

        # Cancel loop task
        t = getattr(self, "_task", None)
        if t and not t.done():
            try:
                t.cancel()
            except Exception:
                pass

    # For multi-symbol debugging
    def __repr__(self) -> str:
        return f"<Orchestrator {self.symbol}>"

    def telemetry(self) -> dict:
        """Return a compact telemetry dict for this orchestrator including
        engine-level risk metrics. Best-effort and non-throwing.
        """
        try:
            return {
                "paused": getattr(self, "is_paused", False),
                "symbol": self.symbol,
                "last_signal": str(getattr(self.engine, "last_signal", None)),
                "last_regime": str(getattr(self.engine, "last_regime", None)),
                # risk telemetry (Phase 3.G)
                "drawdown": float(getattr(self.engine, "current_drawdown", 0)),
                "max_equity_seen": float(getattr(self.engine, "max_equity_seen", 0)),
                "loss_streak": int(getattr(self.engine, "_loss_streak", 0)),
                "risk_off": bool(getattr(self.engine, "risk_off", False)),
                "global_risk_off": bool(getattr(self.engine, "global_risk_off", False)),
                "risk_v2_enabled": bool(getattr(self.engine, "risk_v2_enabled", False)),
                "per_symbol_limit": float(getattr(self.engine, "per_symbol_exposure_limit", 0)),
                "portfolio_limit": float(getattr(self.engine, "global_portfolio_limit", 0)),
            }
        except Exception:
            return {
                "paused": getattr(self, "is_paused", False),
                "symbol": self.symbol,
            }

    async def _run_cycle(self, engine) -> tuple[str, str]:
        """
        Run one decision cycle for this engine.
        Aethelred ExecutionEngine exposes `.run_once(is_mock=False)` which is sync.
        We run it in a threadpool and then collect signal/regime attributes.
        """
        loop = asyncio.get_running_loop()

        def _call():
            # consistent with MultiEngineOrchestrator implementation
            return engine.run_once(is_mock=False)

        # run synchronous engine.run_once in executor
        await loop.run_in_executor(None, _call)

        # engine stores these attrs internally after run_once()
        signal = getattr(engine, "last_signal", "hold")
        regime = getattr(engine, "last_regime", "normal")

        # Ensure per-symbol latency key exists for telemetry consumers
        try:
            self._last_cycle_latency[self.symbol] = self._last_cycle_latency.get(self.symbol, 0)
        except Exception:
            # best-effort: ignore if structure missing
            pass

        return signal, regime

    async def _loop_once(self) -> None:
        """Single-cycle runner. Uses existing `_run_cycle` to call into the
        underlying engine and records telemetry into the shared state store."""
        regime = "normal"
        try:
            cycle_start = time.time()
            # Run the engine cycle
            signal, regime = await self._run_cycle(self.engine)

            # Persist for orchestrator + telemetry
            try:
                self.engine.last_signal = signal
            except Exception:
                pass
            try:
                self.engine.last_regime = regime
            except Exception:
                pass

            # Optional: push telemetry later (Phase D)

            try:
                self.state.mark_run(regime=regime, signal=signal, symbol=self.symbol)
            except TypeError:
                self.state.mark_run(regime=regime, signal=signal)

            try:
                latency_ms = int((time.time() - cycle_start) * 1000)
                self._last_cycle_latency[self.symbol] = latency_ms
                record_event(
                    "cycle",
                    {
                        "symbol": self.symbol,
                        "signal": signal,
                        "regime": regime,
                        "latency_ms": latency_ms,
                    },
                )
                # Emit to Prometheus histogram if available (optional client)
                try:
                    from api.routes import metrics as _metrics

                    _metrics.observe_cycle_latency(self.symbol, latency_ms)
                except Exception:
                    pass
                except Exception:
                    pass

                # --------------------------------------------------------
                # Phase 6.D-1 — Push Risk V3 Gauges (best-effort)
                # --------------------------------------------------------
                try:
                    from api.routes.metrics import (
                        aet_risk_volatility,
                        aet_risk_portfolio_vol,
                        aet_risk_scaling_factor,
                        aet_risk_total_exposure,
                        aet_risk_global_cap,
                        aet_risk_symbol_cap,
                    )

                    if getattr(self.engine, "risk_v3_enabled", False) and getattr(self.engine, "risk_v3", None) is not None:
                        snap = self.engine.risk_v3.telemetry_snapshot()
                        try:
                            aet_risk_volatility.labels(symbol=self.symbol).set(float(snap.get("volatility", 0)))
                        except Exception:
                            pass
                        try:
                            aet_risk_portfolio_vol.labels(symbol=self.symbol).set(float(snap.get("portfolio_vol", 0)))
                        except Exception:
                            pass
                        try:
                            aet_risk_scaling_factor.labels(symbol=self.symbol).set(float(snap.get("scaling_factor", 1)))
                        except Exception:
                            pass
                        try:
                            aet_risk_total_exposure.labels(symbol=self.symbol).set(float(snap.get("total_exposure", 0)))
                        except Exception:
                            pass
                        # configured caps (engine defaults)
                        try:
                            aet_risk_global_cap.labels(symbol=self.symbol).set(float(getattr(self.engine.risk_v3, "global_cap", 0)))
                        except Exception:
                            pass
                        try:
                            aet_risk_symbol_cap.labels(symbol=self.symbol).set(float(getattr(self.engine.risk_v3, "symbol_cap", 0)))
                        except Exception:
                            pass
                except Exception:
                    pass
            except Exception:
                pass

        except Exception:
            # metric: engine error count (best-effort)
            try:
                aet_engine_errors_total.labels(symbol=self.symbol).inc()
            except Exception:
                pass
            # swallow to keep loop alive
            traceback.print_exc()


class MultiEngineOrchestrator:
    """
    Holds a dict of EngineOrchestrator objects keyed by symbol.
    Provides idempotent start_all/stop_all/status methods.
    """

    def __init__(self, orchestrators: Dict[str, EngineOrchestrator]):
        self._orchs = orchestrators
        self._tasks: Dict[str, asyncio.Task] = {}
        self._running: bool = False

        # Added for correctness (these were referenced but never initialized)
        self.queue: asyncio.Queue = asyncio.Queue()
        self._inflight: dict = {}
        self._last_loop_latency_ms: float | None = None
        self.visibility_timeout: float = 30.0
        self.max_attempts: int = 3

        # telemetry & state containers
        self.metrics: dict = {}
        self.state = StateStore()
        self._last_cycle_latency: dict[str, int] = {}
        self.engines = {sym: orch.engine for sym, orch in orchestrators.items()}
        self._logger = logger

    @property
    def symbols(self) -> List[str]:
        return list(self._orchs.keys())

    def status(self) -> Dict[str, str]:
        out = {}
        for sym, orch in self._orchs.items():
            t = self._tasks.get(sym)
            if t and not t.done():
                out[sym] = "running"
            else:
                out[sym] = "stopped"
            # record kill flags into Prometheus gauge (best-effort)
            try:
                kf = getattr(orch, "is_killed", False)
                pf = getattr(orch, "is_paused", False)
                # set labelled values
                try:
                    aet_kill_switch_state.labels(symbol=sym, type="is_killed").set(1 if kf else 0)
                except Exception:
                    pass
                try:
                    aet_kill_switch_state.labels(symbol=sym, type="is_paused").set(1 if pf else 0)
                except Exception:
                    pass
            except Exception:
                pass
        return out

    def risk_off_all(self, value: bool) -> None:
        """Set global risk-off state across all orchestrators and engines.

        This will set a per-orchestrator risk_off flag and also propagate a
        `global_risk_off` attribute onto each engine (used by sizing logic).
        """
        try:
            for sym, orch in self._orchs.items():
                try:
                    orch.set_risk_off(bool(value))
                except Exception:
                    pass

            # also set on engine objects directly for consumers that read it
            for eng in self.engines.values():
                try:
                    setattr(eng, "global_risk_off", bool(value))
                except Exception:
                    pass
        except Exception:
            pass

    async def start_all(self) -> None:
        """
        Idempotent. Starts only orchestrators that are not already running.
        """
        if self._running:
            logger.info("multi_orch_start_all (already running)")
            return

        self._running = True

        for sym, orch in self._orchs.items():
            # Only start new tasks
            if sym not in self._tasks or self._tasks[sym].done():
                logger.info("multi_orch_start", extra={"symbol": sym})
                # ensure per-orch task is created and tracked
                await orch.start()
                self._tasks[sym] = getattr(orch, "_task")

    async def stop_all(self) -> None:
        """
        Cancels all orchestrator tasks. Also idempotent.
        """
        if not self._running:
            logger.info("multi_orch_stop_all (not running)")
            return

        self._running = False

        for sym, task in list(self._tasks.items()):
            if not task.done():
                logger.info("multi_orch_stop", extra={"symbol": sym})
                try:
                    task.cancel()
                except Exception:
                    pass

            # Stop orchestrator loop
            try:
                orch = self._orchs[sym]
                orch.stop()
            except Exception:
                pass

        await asyncio.sleep(0.05)
        self._tasks = {}

    def __repr__(self) -> str:
        return f"MultiEngineOrchestrator(symbols={self.symbols})"

    def prometheus_metrics(self) -> dict[str, float | int | str]:
        """
        Flattened orchestrator + per-symbol metrics for Prometheus.
        Batch 8.
        """
        out: dict[str, float | int | str] = {}

        out["kill_switch"] = 1 if kill_is_on() else 0
        out["orchestrator_queue_length"] = self.queue.qsize()
        out["orchestrator_inflight"] = len(self._inflight)
        if self._last_loop_latency_ms is not None:
            out["orchestrator_loop_latency_ms"] = int(self._last_loop_latency_ms)

        for sym, eng in self.engines.items():
            # prometheus metric labels are encoded into the key here (simple approach)
            prefix = f"engine_{sym}_"
            out[prefix + "signal"] = getattr(eng, "last_signal", "hold")
            out[prefix + "regime"] = getattr(eng, "last_regime", "normal")
            eq = getattr(eng, "equity_now", None)
            if isinstance(eq, (int, float)):
                out[prefix + "equity_now"] = float(eq)
            # per-symbol last cycle latency if available
            if sym in self._last_cycle_latency:
                out[prefix + "cycle_latency_ms"] = int(self._last_cycle_latency.get(sym, 0))

        return out

    async def _manager_loop(self):
        """Manager loop: handle queue, visibility timeouts and write unified snapshots."""
        while self._running:
            try:
                loop_start = time.time()

                # HARD kill: exit immediately
                if kill_is_on() or getattr(self, "is_killed", False):
                    self._running = False
                    break

                # ---- Batch 6B: hardened task retrieval ----
                t = None
                if not self.queue.empty():
                    t = await self.queue.get()

                if t:
                    # register as in-flight
                    try:
                        self._inflight[t.ticket] = {"ts": time.time(), "task": t}
                    except Exception:
                        # ensure ticket presence
                        self._inflight[f"unknown-{int(time.time())}"] = {"ts": time.time(), "task": t}

                    # shutdown request
                    if t.kind == "shutdown":
                        # signal kill to engine loops
                        self.is_killed = True
                        self._running = False
                        break

                    # train request
                    if t.kind == "train":
                        await self._handle_train(t)
                        # remove from inflight
                        self._inflight.pop(t.ticket, None)
                        continue

                # ---- visibility timeout scan ----
                now = time.time()
                expired = []
                for tid, meta in list(self._inflight.items()):
                    if now - meta["ts"] > self.visibility_timeout:
                        expired.append((tid, meta["task"]))

                for tid, task in expired:
                    meta = self._inflight.pop(tid, None)
                    if not meta:
                        continue
                    task.attempts = int(getattr(task, "attempts", 0)) + 1
                    if task.attempts <= self.max_attempts:
                        await self.queue.put(task)
                    else:
                        # else: drop permanently / record failure
                        self.state.record_exception(f"Task {tid} dropped after {task.attempts} attempts")

                # ---- write a unified snapshot for external consumers ----
                try:
                    snapshot = {
                        "kill": kill_is_on(),
                        "orchestrator": {
                            "queue_length": self.queue.qsize(),
                            **self.metrics,
                            "last_cycle_ts": datetime.now(timezone.utc).isoformat(),
                            "symbols_active": list(self.engines.keys()),
                        },
                        "symbols": {},
                    }
                    # per-symbol entries are already in state store; mirror keys here
                    for sym in self.engines.keys():
                        snapshot["symbols"][sym] = {
                            "last_signal": self.state.get("per_symbol", {}).get(sym, {}).get("last_signal"),
                            "last_regime": self.state.get("per_symbol", {}).get(sym, {}).get("last_regime"),
                        }

                    # persist orchestrator-level snapshot
                    try:
                        self.state.update(snapshot)
                    except Exception:
                        pass

                    # telemetry event (snapshot)
                    try:
                        record_event("snapshot", {"symbols": list(self.engines.keys())})
                    except Exception:
                        pass
                except Exception:
                    traceback.print_exc()
                    record_event("exception", {"where": "unified_state_writer"})
                    pass

                # loop latency (ms)
                try:
                    self._last_loop_latency_ms = int((time.time() - loop_start) * 1000)
                except Exception:
                    self._last_loop_latency_ms = None

                await asyncio.sleep(1.0)

            except Exception as e:
                self.state.record_exception(str(e))
                traceback.print_exc()
                await asyncio.sleep(2.0)

    async def _engine_loop(self, engine, symbol: str) -> None:
        """Per-engine loop: runs cycles for a single symbol independently."""
        while self._running and not getattr(self, "is_killed", False):
            if kill_is_on() or getattr(self, "is_killed", False):
                try:
                    self._logger.warning(f"kill_switch_active | stopping loops | {symbol}")
                except Exception:
                    pass
                return

            if getattr(self, "is_paused", False):
                try:
                    self._logger.info(f"paused | skipping cycle | {symbol}")
                except Exception:
                    pass
                await asyncio.sleep(0.3)
                continue

            regime = "normal"
            try:
                cycle_start = time.time()
                signal, regime = await self._run_cycle(engine)

                # per-symbol state
                try:
                    self.state.mark_run(regime=regime, signal=signal, symbol=symbol)
                except TypeError:
                    self.state.mark_run(regime=regime, signal=signal)

                # compute & store per-cycle latency
                try:
                    latency_ms = int((time.time() - cycle_start) * 1000)
                    self._last_cycle_latency[symbol] = latency_ms
                    record_event(
                        "cycle",
                        {
                            "symbol": symbol,
                            "signal": signal,
                            "regime": regime,
                            "latency_ms": latency_ms,
                        },
                    )
                    # Emit to Prometheus histogram if available (optional client)
                    try:
                        from api.routes import metrics as _metrics

                        _metrics.observe_cycle_latency(symbol, latency_ms)
                    except Exception:
                        pass
                except Exception:
                    pass

            except Exception:
                try:
                    self._logger.exception("orchestrator_cycle_error")
                except Exception:
                    pass
                # metric: engine error
                try:
                    aet_engine_errors_total.labels(symbol=symbol).inc()
                except Exception:
                    pass

            # cadence sleep per regime
            sleep_s = CADENCE.get(regime, 3.0)
            await asyncio.sleep(sleep_s)

    # ------------------------------------------------------------
    # Engine cycle wrapper
    # ------------------------------------------------------------

    async def _run_cycle(self, engine) -> tuple[str, str]:
        """Return (signal, regime) for a specific engine instance."""
        # Engine.run_once is sync → run in threadpool
        loop = asyncio.get_running_loop()

        def _call():
            return engine.run_once(is_mock=False)

        await loop.run_in_executor(None, _call)

        # Engine stores regime & signal in shared runtime snapshots
        # but we extract them shallowly from engine if available.
        regime = getattr(engine, "last_regime", "normal")
        signal = getattr(engine, "last_signal", "hold")

        return signal, regime

    # ------------------------------------------------------------
    # Train handler
    # ------------------------------------------------------------

    def _run_train(self, payload: dict):
        """Runs in the loop thread — synchronous."""
        try:
            # attempt to route to an engine-specific enqueue if provided
            fn = getattr(self, "enqueue_train_target", None)
            if callable(fn):
                fn(**payload)
                return

            # fallback: try per-engine enqueue_train on any engine
            for eng in self.engines.values():
                fn2 = getattr(eng, "enqueue_train", None)
                if fn2:
                    fn2(**payload)
                    return
        except Exception:
            traceback.print_exc()

    async def _handle_train(self, task: Task):
        """
        Wrapper for retry-safe train task handling.
        """
        try:
            self._run_train(task.payload)
        except Exception:
            # retry path
            task.attempts = int(getattr(task, "attempts", 0)) + 1
            if task.attempts <= self.max_attempts:
                await self.queue.put(task)
            else:
                self.state.record_exception(f"train task {task.ticket} failed after {task.attempts} attempts")

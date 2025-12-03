import asyncio
import time

from api.bootstrap_real_engine import services_or_none
from ops.notifier import get_notifier
from utils.logger import logger, log_extra


SLOW_FACTOR = 2.0  # slow cycle threshold multiplier
INTERVAL_SEC = 5.0  # watchdog check interval


async def watchdog_loop() -> None:
    """
    Main watchdog coroutine.
    Periodically inspects orchestrators, engines, and exchange health.
    Safe in paper mode. Never throws.
    """
    notifier = get_notifier()

    while True:
        try:
            sv = services_or_none()
            if sv is None:
                await asyncio.sleep(INTERVAL_SEC)
                continue

            orch = getattr(sv, "multi_orch", None)
            exchange = getattr(sv, "exchange", None)

            if orch:
                _check_engines(orch, notifier)

            # increment watchdog checks metric
            try:
                try:
                    from api.routes import metrics as _metrics
                except Exception:
                    _metrics = None
                if _metrics is not None and getattr(_metrics, "aet_watchdog_checks_total", None) is not None:
                    try:
                        _metrics.aet_watchdog_checks_total.inc()
                    except Exception:
                        pass
            except Exception:
                pass

            if exchange:
                await _check_exchange(exchange, notifier)

        except Exception as e:
            try:
                logger.error("watchdog_error", **log_extra(err=str(e)))
            except Exception:
                pass

        await asyncio.sleep(INTERVAL_SEC)


def _check_engines(orch, notifier) -> None:
    """
    Check cycle latency and stall detection for each symbol engine.
    Uses best-effort attribute access to avoid coupling to a single orchestrator impl.
    """
    now = time.time()

    # try multiple strategies to read per-symbol timing
    # 1) MultiEngineOrchestrator: orch._orchs -> per-symbol EngineOrchestrator
    try:
        orches = getattr(orch, "_orchs", None)
        if orches is None:
            # fallback: maybe orch.engines dict exists
            orches = {k: None for k in getattr(orch, "engines", {}).keys()}

        for sym, orch_obj in orches.items() if isinstance(orches, dict) else []:
            try:
                # prefer orchestrator-level metrics
                last_ts = None
                last_ms = None
                cycle_delay = 2.0

                if orch_obj is not None:
                    # EngineOrchestrator stores _last_cycle_latency dict
                    try:
                        last_ms = (
                            orch_obj._last_cycle_latency.get(sym) if hasattr(orch_obj, "_last_cycle_latency") else None
                        )
                    except Exception:
                        last_ms = None
                    # no timestamp available on EngineOrchestrator; try shared state
                    try:
                        last_ts = getattr(orch_obj, "last_cycle_ts", None)
                    except Exception:
                        last_ts = None
                    # cycle_delay may be an attribute on engine
                    try:
                        cycle_delay = float(getattr(orch_obj.engine, "cycle_delay", 2.0))
                    except Exception:
                        cycle_delay = 2.0
                else:
                    # fallback: check MultiEngineOrchestrator maps
                    try:
                        last_ms = orch._last_cycle_latency.get(sym)
                    except Exception:
                        last_ms = None

                # Stall detection: if we have a last_ts and it's too old
                if last_ts and (now - last_ts) > (2 * cycle_delay):
                    try:
                        notifier.send("watchdog_stall", symbol=sym, stalled_for=now - last_ts)
                    except Exception:
                        pass

                # Slow-cycle detection
                if last_ms and last_ms > (cycle_delay * 1000 * SLOW_FACTOR):
                    try:
                        notifier.send("watchdog_slow_cycle", symbol=sym, duration_ms=last_ms)
                    except Exception:
                        pass

            except Exception:
                # per-symbol guard
                pass
    except Exception:
        # best-effort; do not raise
        pass


async def _check_exchange(exchange, notifier) -> None:
    """
    Probe exchange health.
    """
    try:
        # prefer async health_probe if available
        if hasattr(exchange, "health_probe"):
            try:
                await exchange.health_probe()
            except Exception:
                notifier.send("exchange_unhealthy")
        else:
            # no async probe available; skip
            pass
    except Exception:
        try:
            notifier.send("exchange_unhealthy")
        except Exception:
            pass

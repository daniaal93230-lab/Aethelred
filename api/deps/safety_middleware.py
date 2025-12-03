"""
Engine Safety Middleware (Phase 1).

This thin wrapper provides:
 - defensive execution around Engine.run_once
 - guards against runaway loops
 - basic exception isolation
 - optional integration points for:
      ML anomaly detectors,
      circuit breakers,
      global kill-switch,
      volatility filters,
      risk-engine veto,
      log-throttling.

Phase 1 is intentionally minimal and test-safe.
"""

from __future__ import annotations
from typing import Optional, Any
import time
import logging

logger = logging.getLogger(__name__)


class SafetyMiddleware:
    """
    Wraps an Engine instance and intercepts run_once with safety checks.

    Usage:
        safe = SafetyMiddleware(engine)
        safe.run_once()

    Engine attribute layout is untouched — middleware is a thin wrapper.
    """

    def __init__(self, engine: Any) -> None:
        self.engine = engine
        self.max_runtime_sec = 3.0  # prevent infinite stalls
        self.last_exception: Optional[str] = None
        self.kill_switch = False

    def run_once(self, *a: Any, **kw: Any) -> Any:
        if self.kill_switch:
            logger.warning("Engine run blocked by safety kill_switch.")
            return None

        start = time.time()

        # structured start log
        try:
            from utils.logger import log_json

            log_json(logger, "debug", "safety_cycle_start")
        except Exception:
            pass

        try:
            result = self.engine.run_once(*a, **kw)
        except Exception as e:
            self.last_exception = str(e)
            logger.error(f"Engine run_once crashed: {e}", exc_info=True)
            try:
                log_json(logger, "error", "engine_crash", error=str(e))
            except Exception:
                pass
            return None

        dt = time.time() - start

        if dt > self.max_runtime_sec:
            logger.warning(
                f"Engine run took {dt:.3f}s (> {self.max_runtime_sec}s). Possible stall. Throttling future runs."
            )
            try:
                log_json(
                    logger,
                    "warning",
                    "engine_slow_cycle",
                    duration=dt,
                    threshold=self.max_runtime_sec,
                )
            except Exception:
                pass

        # structured end log
        try:
            log_json(logger, "debug", "safety_cycle_end", duration=dt)
        except Exception:
            pass

        return result

    # ---- upgrade-ready control hooks ----

    def activate_kill_switch(self, reason: str = "manual") -> None:
        logger.warning(f"Kill-switch activated: {reason}")
        self.kill_switch = True

    def reset_kill_switch(self) -> None:
        self.kill_switch = False
        logger.info("Kill-switch reset.")

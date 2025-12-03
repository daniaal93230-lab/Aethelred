"""Prometheus metrics helper (lazy, optional).

Provides a singleton Registry and helpers to observe metrics without
requiring prometheus_client at import time. All functions are no-ops
when prometheus_client is not installed so tests remain lightweight.
"""

from __future__ import annotations

from typing import Any
import threading

# module-level placeholders
_registry = None
_histograms: dict[str, Any] = {}
_lock = threading.Lock()

# Metric family placeholders (populated when prometheus_client is available)
aet_regime_total = None
aet_ml_veto_total = None
aet_orders_total = None
aet_orders_last_min = None
aet_consec_loss = None
aet_drawdown_pct = None
aet_kill_switch_state = None
aet_volatility_anomaly_total = None
aet_engine_errors_total = None
# additional families added in final polish
aet_uptime_seconds_total = None
aet_watchdog_checks_total = None
aet_orch_cycles_total = None
# Risk V3 metrics
aet_risk_volatility = None
aet_risk_portfolio_vol = None
aet_risk_scaling_factor = None
aet_risk_global_cap = None
aet_risk_symbol_cap = None
aet_risk_total_exposure = None


def _safe_import_prometheus():
    """Attempt to import prometheus_client lazily.
    Returns the module or None if not present.
    """
    try:
        import prometheus_client as _pc

        return _pc
    except Exception:
        return None


def get_registry():
    """Return a CollectorRegistry singleton, or None if prometheus_client
    isn't available.
    """
    global _registry
    if _registry is not None:
        return _registry

    pc = _safe_import_prometheus()
    if pc is None:
        return None

    with _lock:
        if _registry is None:
            _registry = pc.core.Registry() if hasattr(pc, "core") else pc.CollectorRegistry()
            # populate standard metric families now that we have a registry
            _ensure_metric_families(pc, _registry)
    return _registry


def _ensure_metric_families(pc, reg):
    """Create module-level metric families if they are not already set.
    This function is idempotent and safe to call multiple times.
    """
    global \
        aet_regime_total, \
        aet_ml_veto_total, \
        aet_orders_total, \
        aet_orders_last_min, \
        aet_consec_loss, \
        aet_drawdown_pct, \
        aet_kill_switch_state, \
        aet_volatility_anomaly_total, \
        aet_engine_errors_total, \
        aet_uptime_seconds_total, \
        aet_watchdog_checks_total, \
        aet_orch_cycles_total, \
        aet_risk_volatility, \
        aet_risk_portfolio_vol, \
        aet_risk_scaling_factor, \
        aet_risk_global_cap, \
        aet_risk_symbol_cap, \
        aet_risk_total_exposure

    # If prometheus client not available, bail
    if pc is None:
        return

    try:
        if aet_regime_total is None:
            aet_regime_total = pc.Counter(
                "aet_regime_total",
                "Count of regimes observed",
                ["symbol", "regime"],
                registry=reg,
            )
    except Exception:
        aet_regime_total = None

    try:
        if aet_ml_veto_total is None:
            aet_ml_veto_total = pc.Counter(
                "aet_ml_veto_total",
                "Count of ML veto events",
                ["symbol", "reason"],
                registry=reg,
            )
    except Exception:
        aet_ml_veto_total = None

    try:
        if aet_orders_total is None:
            aet_orders_total = pc.Counter(
                "aet_orders_total",
                "Orders executed",
                ["symbol", "side"],
                registry=reg,
            )
    except Exception:
        aet_orders_total = None

    try:
        if aet_orders_last_min is None:
            aet_orders_last_min = pc.Gauge(
                "aet_orders_last_min",
                "Orders executed in last 60 seconds (rolling)",
                ["symbol"],
                registry=reg,
            )
    except Exception:
        aet_orders_last_min = None

    try:
        if aet_consec_loss is None:
            aet_consec_loss = pc.Gauge(
                "aet_consec_loss",
                "Consecutive losing trades",
                ["symbol"],
                registry=reg,
            )
    except Exception:
        aet_consec_loss = None

    try:
        if aet_drawdown_pct is None:
            aet_drawdown_pct = pc.Gauge(
                "aet_drawdown_pct",
                "Current portfolio drawdown from peak (0.0 to 1.0)",
                registry=reg,
            )
    except Exception:
        aet_drawdown_pct = None

    try:
        if aet_kill_switch_state is None:
            aet_kill_switch_state = pc.Gauge(
                "aet_kill_switch_state",
                "Kill switch states per symbol",
                ["symbol", "type"],
                registry=reg,
            )
    except Exception:
        aet_kill_switch_state = None

    try:
        if aet_volatility_anomaly_total is None:
            aet_volatility_anomaly_total = pc.Counter(
                "aet_volatility_anomaly_total",
                "Unusual volatility spikes detected",
                ["symbol"],
                registry=reg,
            )
    except Exception:
        aet_volatility_anomaly_total = None

    try:
        if aet_engine_errors_total is None:
            aet_engine_errors_total = pc.Counter(
                "aet_engine_errors_total",
                "Engine loop runtime errors",
                ["symbol"],
                registry=reg,
            )
    except Exception:
        aet_engine_errors_total = None

    # uptime gauge
    try:
        if aet_uptime_seconds_total is None:
            aet_uptime_seconds_total = pc.Gauge(
                "aet_uptime_seconds_total",
                "Process uptime in seconds (best-effort)",
                registry=reg,
            )
    except Exception:
        aet_uptime_seconds_total = None

    try:
        if aet_watchdog_checks_total is None:
            aet_watchdog_checks_total = pc.Counter(
                "aet_watchdog_checks_total",
                "Watchdog check iterations",
                registry=reg,
            )
    except Exception:
        aet_watchdog_checks_total = None

    try:
        if aet_orch_cycles_total is None:
            aet_orch_cycles_total = pc.Counter(
                "aet_orch_cycles_total",
                "Orchestrator cycles completed",
                ["symbol"],
                registry=reg,
            )
    except Exception:
        aet_orch_cycles_total = None

    # -------------------------------------------------------------
    # Phase 6.D-1 — Risk Engine V3 Telemetry Gauges
    # -------------------------------------------------------------
    try:
        if aet_risk_volatility is None:
            aet_risk_volatility = pc.Gauge(
                "aet_risk_volatility",
                "Symbol realized volatility (RiskEngineV3)",
                ["symbol"],
                registry=reg,
            )
    except Exception:
        aet_risk_volatility = None

    try:
        if aet_risk_portfolio_vol is None:
            aet_risk_portfolio_vol = pc.Gauge(
                "aet_risk_portfolio_vol",
                "Portfolio realized volatility (RiskEngineV3)",
                ["symbol"],
                registry=reg,
            )
    except Exception:
        aet_risk_portfolio_vol = None

    try:
        if aet_risk_scaling_factor is None:
            aet_risk_scaling_factor = pc.Gauge(
                "aet_risk_scaling_factor",
                "RiskEngineV3 volatility scaling factor",
                ["symbol"],
                registry=reg,
            )
    except Exception:
        aet_risk_scaling_factor = None

    try:
        if aet_risk_total_exposure is None:
            aet_risk_total_exposure = pc.Gauge(
                "aet_risk_total_exposure",
                "Total exposure snapshot from RiskEngineV3",
                ["symbol"],
                registry=reg,
            )
    except Exception:
        aet_risk_total_exposure = None

    try:
        if aet_risk_global_cap is None:
            aet_risk_global_cap = pc.Gauge(
                "aet_risk_global_cap",
                "RiskEngineV3 configured global cap (fraction)",
                ["symbol"],
                registry=reg,
            )
    except Exception:
        aet_risk_global_cap = None

    try:
        if aet_risk_symbol_cap is None:
            aet_risk_symbol_cap = pc.Gauge(
                "aet_risk_symbol_cap",
                "RiskEngineV3 configured symbol cap (fraction)",
                ["symbol"],
                registry=reg,
            )
    except Exception:
        aet_risk_symbol_cap = None


def observe_cycle_latency(symbol: str, latency_ms: int) -> None:
    """Observe a cycle latency value for the given symbol into a
    Histogram metric. No-op if prometheus_client is unavailable.
    """
    pc = _safe_import_prometheus()
    if pc is None:
        return

    reg = get_registry()
    if reg is None:
        return

    # sanitize symbol for label usage
    label = str(symbol).replace("/", "_").replace("-", "_")
    name = "orchestrator_cycle_latency_ms"

    # create a labeled histogram per-symbol (avoid dynamic label creation)
    key = f"{name}:{label}"
    if key not in _histograms:
        with _lock:
            if key not in _histograms:
                try:
                    # create a simple histogram with a 'symbol' label
                    h = pc.Histogram(name, "Orchestrator cycle latency (ms)", labelnames=("symbol",), registry=reg)
                    _histograms[key] = h
                except Exception:
                    # fallback: try to create without labels (older client)
                    try:
                        h = pc.Histogram(name, "Orchestrator cycle latency (ms)", registry=reg)
                        _histograms[key] = h
                    except Exception:
                        _histograms[key] = None

    h = _histograms.get(key)
    if h:
        try:
            # If histogram was created with labels, use labeled instance
            if hasattr(h, "labels"):
                h.labels(symbol=label).observe(float(latency_ms))
            else:
                h.observe(float(latency_ms))
        except Exception:
            pass


def generate_metrics_text() -> str:
    """Return Prometheus text format for the registry, or empty string
    if the client is not available.
    """
    pc = _safe_import_prometheus()
    if pc is None:
        return ""

    reg = get_registry()
    if reg is None:
        return ""

    try:
        # generate_latest returns bytes
        out = pc.generate_latest(reg)
        return out.decode("utf-8") if isinstance(out, (bytes, bytearray)) else str(out)
    except Exception:
        return ""

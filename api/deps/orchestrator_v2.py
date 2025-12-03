from __future__ import annotations

from core.orchestrator_v2 import OrchestratorV2
from core.telemetry_bus_v2 import TelemetryBusV2
from core.telemetry_history_v2 import TelemetryHistoryV2

# Global orchestrator instance for API layer
_telemetry_bus = TelemetryBusV2()
_history = TelemetryHistoryV2()
_orchestrator = OrchestratorV2(telemetry_bus=_telemetry_bus, history=_history)


def get_orchestrator() -> OrchestratorV2:
    """Dependency for routes."""
    return _orchestrator


def get_telemetry_bus() -> TelemetryBusV2:
    return _telemetry_bus

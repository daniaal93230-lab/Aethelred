"""
DI shim exposing the EngineOrchestrator type.

This module re-exports the concrete orchestrator implementation from
`api.core.orchestrator` as `EngineOrchestrator` so other DI consumers
can perform isinstance checks without importing core internals.
"""

from api.core.orchestrator import EngineOrchestrator

__all__ = ["EngineOrchestrator"]

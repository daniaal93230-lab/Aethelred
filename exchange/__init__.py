"""
Canonical exchange shim for legacy compatibility.

This module re-exports the canonical PaperExchange implementation so
legacy imports that expect `Exchange` continue to function during the
staged purge of the old `bot/` package.
"""

from .paper import PaperExchange

# Backwards-compatible alias used across the codebase
Exchange = PaperExchange

__all__ = ["PaperExchange", "Exchange"]

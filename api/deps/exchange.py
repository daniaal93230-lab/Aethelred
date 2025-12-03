from __future__ import annotations

from typing import Any

from api.deps.settings import Settings

# Re-use existing compatibility export in the canonical `exchange` package which
# re-exports exchange.paper.PaperExchange when available and provides a minimal
# fallback. Prefer `exchange` shim over the legacy `bot.exchange` module.
from exchange import Exchange  # live CCXT wrapper
from exchange.paper import PaperExchange  # canonical paper exchange


def init_exchange(settings: Settings) -> Any:
    """
    Initialize and return an exchange instance based on settings.

    If settings.PAPER is truthy we return a PaperExchange, otherwise a live
    Exchange wrapper. Keep this simple — the ExecutionEngine or callers can
    wrap or configure further as needed.
    """
    # Use canonical PaperExchange during PAPER mode
    if getattr(settings, "PAPER", False):
        return PaperExchange()
    return Exchange()


def get_paper_exchange() -> PaperExchange:
    """
    Legacy compatibility helper for demo routes and old tests.
    Returns a fresh PaperExchange instance.
    Safe to keep — not used by orchestrator.
    """
    return PaperExchange()


def get_live_exchange() -> Exchange:
    """
    Legacy compatibility helper for demo routes and old tests.
    Returns a fresh Exchange instance.
    """
    return Exchange()


__all__ = ["init_exchange", "get_paper_exchange", "get_live_exchange"]

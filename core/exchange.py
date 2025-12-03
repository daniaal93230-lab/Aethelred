#
# Canonical unified PaperExchange model
# Tests, engine, orchestrator and endpoints should
# ALWAYS import from core.exchange.PaperExchange.
#
from typing import Any

try:
    from exchange.paper import PaperExchange as _ExtPaper  # type: ignore
    PaperExchange = _ExtPaper
except Exception:
    # Very minimal fallback — used only if external import unavailable.
    class PaperExchange:   # noqa: D401
        """
        FALLBACK STUB — DO NOT EXTEND.
        Only exists so imports do not explode during test bootstrap.
        """
        def __init__(self, *args: Any, **kwargs: Any):
            self._orders: list[dict] = []

        def place_order(self, *args: Any, **kwargs: Any) -> dict:
            out = {"status": "placed", "args": args, "kwargs": kwargs}
            self._orders.append(out)
            return out

        def cancel_order(self, *args: Any, **kwargs: Any) -> bool:
            return True

        def fetch_balance(self) -> dict:
            return {"free": {}, "used": {}, "total": {}}

__all__ = ["PaperExchange"]

from __future__ import annotations
from typing import Protocol, Dict, Any
from .types import Signal

class Strategy(Protocol):
    name: str  # short human readable, used in decisions.csv
    def prepare(self, ctx: Dict[str, Any]) -> None: ...
    def generate_signal(self, market_state: Dict[str, Any]) -> Signal: ...

class NullStrategy:
    name = "null"
    def __init__(self, ttl: int = 1) -> None:
        self.ttl = ttl
    def prepare(self, ctx):
        return None
    def generate_signal(self, market_state):
        from .types import Signal
        return Signal.hold(self.ttl)

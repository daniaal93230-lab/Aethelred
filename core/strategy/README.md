Strategy subpackage

Houses the Strategy Protocol, Signal types, and adapter implementations.

Key files:
- `core/strategy/types.py` — `Signal` dataclass and `Side` enum.
- `core/strategy/base.py` — `Strategy` protocol and `NullStrategy`.
- `core/strategy/selector.py` — `StrategySelector` to register/pick adapters by regime.
- `core/strategy/*_adapter.py` — example adapters (MA crossover, RSI mean revert, Donchian).

For LLMs: read `core/strategy/types.py` and `core/strategy/base.py` to find the logging contract used by adapters.

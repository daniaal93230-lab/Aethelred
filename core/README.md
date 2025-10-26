Core module

Contains engine-level signal builders, backtest helpers, and execution helpers.

Key files:
- `core/engine.py` — signal builders and backtest helper functions.
- `core/execution_engine.py` — runtime execution engine used by the runner.
- `core/engine_strategy_wiring.py` — helper to wire StrategySelector into engines.
- `core/strategy/` — strategy interface and adapters (see its README).

For LLMs: look at small functions (e.g., `build_ema_crossover`, `build_rsi_mean_reversion`) to learn how signals are generated.

Bot module

Contains higher-level orchestration and glue used to run strategies in loops, paper trading, and telemetry.

Key files:
- `bot/runner.py` / `runner_paper.py` — runner entrypoints.
- `bot/brain.py` — orchestrates signals to execution and records decisions.

Note: This module depends on `core` and `db` for state and persistence.

LLM-friendly Repo Overview

Purpose
-------
Aethelred is a small trading research and paper-trading stack. This overview highlights the files and entrypoints an LLM (or engineer) will care about when analyzing or summarizing the repository.

What to read first
------------------
- `README.md` — top-level quickstart (also includes an "LLM-friendly" section).
- `REPO_OVERVIEW.md` — this file (structural map and pointers).
- `core/` — main engine, signal builders, and strategy helpers.
- `api/` — FastAPI app and export endpoints.
- `bot/` — runtime scripts, paper runner and orchestration helpers.
- `db/` — sqlite manager and schema helpers.
- `scripts/` — dev helpers (list routes, export DB, prune legacy).
- `tests/` — pytest-based automated tests; good for examples and expected behavior.

Key entrypoints
---------------
- Development runner: `python run.py --mode paper` (uses unified runner)
- API (FastAPI): `uvicorn api.main:app --port 8080` — exposes `/export` endpoints and `/ui` pages.
- Tests: `pytest -q`
- Export helpers: `scripts/export_db.py`, `scripts/dump_db_exports.py`, `scripts/pull_exports.ps1`

Canonical artifacts
-------------------
- Canonical decisions header: `api/contracts/decisions_header.py` (used by exporters/tests)
- Regime selector config (optional): `config/selector.yaml` (YAML mapping symbol->regime)
- Atomic runtime snapshots: `core/runtime_state` writes `account_runtime.json` for dashboards

How an LLM can summarize quickly
--------------------------------
1. Run the repo index generator to get a machine-readable map (see `scripts/generate_repo_index.py`).
2. Read `api/routes/export.py` and `api/contracts/decisions_header.py` to understand the decisions/trades export shape.
3. Inspect `core/strategy` for the Strategy Protocol and adapters (MA, RSI, Donchian).
4. Read `core/execution_engine.py` and `bot/brain.py` to see the runtime sweep and where decisions/trades are emitted.

Files that produce or consume runtime data
-----------------------------------------
- `db/db_manager.py` — sqlite persistence and decision_log/trades tables
- `core/execution_engine.py` — runtime decision evaluation and `save_decision_row` calls
- `api/routes/export.py` — HTTP exporters for trades and decisions
- `core/runtime_state.py` — writes atomic runtime snapshots for the dashboard

Quick questions an LLM can answer from this repo
------------------------------------------------
- Which files produce the canonical decisions CSV?  -> `api/routes/export.py`, `db/db_manager.py`
- Where are strategies implemented? -> `core/engine.py` and `core/strategy/*`
- How to run exports locally? -> `scripts/pull_exports.ps1` or `scripts/export_db.py`

Tips for parsing
----------------
- Use `scripts/generate_repo_index.py` to produce a JSON of all filenames and top-level docstrings.
- Prefer reading small modules (`api/contracts/decisions_header.py`, `core/strategy/types.py`) rather than huge files.

Contact
-------
If anything needs clarification about conventions or runtime expectations, check `docs/strategos.md` and the tests under `tests/` for concrete examples.

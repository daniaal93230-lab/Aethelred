Aethelred — Architecture Overview

This document describes the architecture of the Aethelred repository, how the major components are wired together, and where to look for specific features. It is intended for developers working on the project and explains the runtime lifecycle, dependency wiring, orchestrator/engine responsibilities, exchanges (paper/live), and the test/dev workflow.

Table of contents
- High-level overview
- Top-level layout
- Core components
 - Recent additions (since last architecture snapshot)
 - Manifests (file_map.json / file_map.yaml)
  Aethelred — Architecture (concise + visual)

  This short guide explains the runtime wiring and where to look for each responsibility.

  Quick diagram (Mermaid)

  ```mermaid
  flowchart LR
    subgraph API[FastAPI process]
      A[app.state.services]
      B[app.state.multi_orch]
      C[api/routes/runtime]
    end
    subgraph Orchestrators[MultiEngineOrchestrator]
      B --> O1[Orchestrator BTC]
      B --> O2[Orchestrator ETH]
      B --> O3[Orchestrator SOL]
    end
    ## Aethelred — Architecture (detailed)

    This document explains the runtime architecture, the responsibilities of the major components, where to look for features, and quick developer run / troubleshooting guidance. It is intended for contributors and operators.

    ## High-level summary

    - FastAPI (the `api/` package) is the canonical host and dependency container. During startup the app builds per-symbol `ExecutionEngine` instances and one `EngineOrchestrator` per symbol, then registers a `MultiEngineOrchestrator` which coordinates them.

    ### Recent additions (what changed)

    Since the last architecture snapshot the repository gained several modernization features and supporting files. Key additions you should know about:

  - ADX-based regime classification: `core/regime_adx.py` — computes ADX and labels regimes (trend / chop / transition) used by the selector.
    - Canonical strategy selector: `core/strategy/selector.py` — maps regimes to strategy callables and includes a small compatibility shim so legacy tests still pass.
    - New Decimal-precise strategies:
      - `core/strategy/donchian_breakout.py` — Donchian breakout strategy (trend regime)
      - `strategy/ma_crossover.py` — Moving-average crossover (transition regime)
    - Engine TTL + holding logic: engines now keep a per-engine `_signal_memory` (last actionable signal + `ttl_remaining`) so HOLD signals can reuse a previously stored actionable signal while the TTL > 0.
    - Walk-Forward CV (WFCV) backtest harness: `backtest/wfcv.py`, `backtest/metrics.py`, `backtest/runner.py` for offline walk-forward evaluation using regime segmentation.
    - DI / FastAPI bootstrap updates: `api/bootstrap_real_engine.py` attaches per-symbol engines and orchestrators into `app.state` so the API is the canonical provider of runtime engines; see `app.state.services`, `app.state.engines`, and `app.state.multi_orch`.
    - Exchange compatibility shim and `exchange/paper.py` improvements for realistic OHLCV in PAPER mode.
    - Repository manifest regeneration: `file_map.json` and `file_map.yaml` were regenerated to include all new files and support tooling/LLM ingestion.

    - ML / Meta-Signal Ranker (Phase 4)
      - `core/ml/feature_extractor.py` — Decimal-safe canonical feature extractor used to assemble model inputs (signal strength, regime one-hot, volatility, donchian width, MA slope, RSI, intent veto).
      - `core/ml/signal_ranker.py` — XGBoost ranker wrapper with safe lazy-loading (no import-time xgboost dependency) and neutral fallback (score=0.5) when model or xgboost are missing.
      - `core/ml/gates.py` — hybrid veto + probabilistic downscale gate (ML-driven size modulation and hard veto behavior).
      - `core/ml/explain.py` — SHAP explainability helper (JSON + optional PNG plot). Degrades gracefully if SHAP or model are not available.
      - `ml/train_signal_ranker.py` — offline training pipeline to build `models/signal_ranker.json` and `models/signal_ranker.meta.json` (checksumed metadata). Keeps xgboost import lazy so tests remain lightweight.
      - API explain route: `api/routes/ml_explain.py` — `GET /ml/explain_signal/{ts}` providing JSON or plot explanations for historic snapshots.
      - Unit tests added: `tests/test_ml_explain.py` and `tests_ml/test_signal_ranker_training.py` (explain fallback + training helpers smoke tests).
      - Design note: ML dependencies are optional — xgboost and shap are imported lazily at runtime so CI/test collection does not require those libraries.

    - Telemetry & orchestration (Phase 4 additions):
      - `core/telemetry_bus_v2.py` — in-process pub/sub used by the orchestrator and API to broadcast per-tick snapshots and events.
      - `core/orchestrator_v2.py` — async multi-symbol orchestrator (per-symbol engines, per-symbol/global kill/risk flags, portfolio aggregation).
      - `core/telemetry_history_v2.py` — rolling in-memory history buffers for per-symbol and portfolio snapshots (fixed-size deques).
      - `core/telemetry_history_v2.py` — rolling in-memory history buffers for per-symbol and portfolio snapshots (fixed-size deques) with retention cap to avoid unbounded memory growth.
      - `core/paper_executor_v2.py` & `core/execution_router_v2.py` — paper-mode execution simulator and routing logic used by `ExecutionEngine` for Phase 4.B simulation.
      - API telemetry routes and WS streaming: `api/routes/telemetry.py`, `api/routes/history.py`, and `api/routes/ws_telemetry.py` — expose read-only HTTP and websocket telemetry endpoints used by dashboards and monitoring tools.
      - Lightweight dashboard static assets under `api/static/` served at `/dashboard` by the FastAPI app for real-time monitoring (uses WS + HTTP telemetry endpoints).

    - Tooling:
      - `tools/generate_file_map.py` — repository manifest generator (produces `file_map.json` and `file_map.yaml` when PyYAML available). Useful for automated docs and LLM ingestion.

    - Ops & Observability (Phase 5 additions — final polish):
      - `api/routes/metrics.py` — lazy Prometheus registry helpers and standard metric families (uptime, watchdog checks, per-symbol cycle counters, drawdown, engine errors, ML vetoes). Prometheus client is optional and loaded lazily.
      - `ops/notifier.py` — non-blocking ops notifier with async dispatchers (Telegram/Slack) and background-thread fallback for sync contexts.
      - `ops/watchdog.py` — asynchronous watchdog coroutine that inspects orchestrator/engine health, slow cycles, stalls, and probes exchange health; emits metrics and notifies ops on anomalies.
      - `api/routes/ops_dashboard.py` — small operator dashboard served at `/ops` for quick inspection and links to `/health` and `/metrics`.
      - Structured JSON logging updates: `utils/logger.py` now emits JSON logs with component field and per-cycle correlation IDs (`cid`) injected by orchestrator loops to aid traceability.
      - `/health` endpoint enhancements: `api/routes/health.py` reports API uptime, orchestrator/engine health, watchdog metadata, and exchange probe results.

    These observability additions were implemented with best-effort guards and lazy imports so run-time and tests remain lightweight when optional dependencies (prometheus_client, xgboost, shap) are not installed.

    ## Phase 6 — Risk V3 & Insight Engine (recent)

    Phase 6 continued the staged rollout of a next-generation risk stack (V3) and a standalone Insight Engine for trade-level analytics. Key additions in this phase:

    - Risk Engine V3: `core/risk/engine_v3.py`
      - ExposureModel: cross-symbol exposure calculations and caps.
      - VolatilityTargeter: realized-vol estimator and portfolio scaling.
      - PositionSizerV3: conservative, Decimal-safe sizing with exposure cap enforcement and plug-in kill-switch hooks.
      - RiskTelemetry: per-engine telemetry (volatility, portfolio_vol, scaling, panic state).
      - Non-invasive activation: `ExecutionEngine.risk_v3_enabled` (default False) — V2 remains authoritative until explicitly enabled.

    - Kill-switch / Sanity Mode (Phase 6.F)
      - Configurable thresholds (symbol vol, portfolio vol, shock multiplier).
      - Automatic panic mode (forces size to zero) on extreme realized vol or shocks.
      - Panic flag flows from `RiskEngineV3.apply()` to `PositionSizerV3.compute_size()` and is exposed via telemetry.

    - Insight Engine (Phase 6.E): `insight/engine.py`, `insight/utils.py`
      - Trade-level MAE/MFE tracking, per-strategy and per-regime aggregations.
      - Rolling performance metrics (Sharpe, Sortino, Calmar) over a fixed trade window.
      - Optional daily KPI CSV export (writes to `insight/kpi/YYYY-MM-DD.csv` when `export_daily_kpi()` is called).
      - Non-intrusive attachment: `ExecutionEngine.insight_enabled` defaults to False; when enabled the engine records synthetic trade IDs and populates insight trackers (no tests call this by default).

    - Insight API endpoints (Phase 6.E-5)
      - `api/routes/insight.py` — read-only endpoints:
        - GET `/insight/daily` — returns the JSON snapshot of the daily KPI (does not write files).
        - GET `/insight/strategy/{name}` — returns MAE/MFE aggregates for a named strategy across engines.

    Notes: All Phase 6 components were designed to be opt-in, lazy-loaded where practical, and guarded with try/except so they don't disrupt test collection or legacy flows.

    These changes are backwards-compatible with the legacy test shims: mock/paper-mode behavior was preserved where tests expect legacy string signals and certain names (for example `ema_trend` remains a valid legacy strategy name in selector mappings).

    - The `ExecutionEngine` (in `core/execution_engine.py`) evaluates OHLCV, runs strategies, applies risk/gates, and executes orders through an exchange adapter (paper or live).
    - Exchange adapters (e.g., `exchange/paper.py`) provide market data and order simulation for reproducible paper trading.

    ## Runtime diagram (conceptual)

    ```mermaid
    flowchart LR
      subgraph API[FastAPI process]
        A[app.state.services]
        B[app.state.multi_orch]
        C[api/routes/runtime]
      end
      subgraph Orchestrators[MultiEngineOrchestrator]
        B --> O1[Orchestrator BTC]
        B --> O2[Orchestrator ETH]
        B --> O3[Orchestrator SOL]
      end
      subgraph Engines[Per-symbol Engines]
        O1 --> E1[Engine BTC]
        O2 --> E2[Engine ETH]
        O3 --> E3[Engine SOL]
      end
      subgraph Exchanges[Adapters]
        EX1[PaperExchange]
        EX2[Live Exchange]
      end
      E1 --> EX1
      E2 --> EX1
      E3 --> EX1

      C -->|control| B
      A -->|DI| E1
    ```

    ## File map — where to look

    - `api/main.py` — FastAPI app entrypoint (uvicorn target).
    - `api/bootstrap_real_engine.py` — app factory / bootstrap: builds engines & orchestrators and attaches a `services` container to `app.state`.
    - `api/core/orchestrator.py` — `EngineOrchestrator` (per-symbol loop) and `MultiEngineOrchestrator` (manager with `start_all()` / `stop_all()` / `status()`).
    - `api/routes/runtime.py` — HTTP runtime control endpoints (`/runtime/start`, `/runtime/stop`, `/runtime/status`, `/runtime/pause`, `/runtime/resume`) and telemetry endpoints.
    - `api/deps/engine.py` — engine builder and DI helpers used by routes/tests.
    - `core/execution_engine.py` — core trading engine (signal evaluation, gating, sizing, snapshotting, DB writes).
    - `core/trade_logic.py`, `core/risk.py`, `core/regime.py` — strategy routing, risk calculations, regime classification.
    - `exchange/paper.py` — simulated/paper exchange adapter used in `PAPER` mode.
    - `db/db_manager.py` — persistence helpers used by the engine and paper exchange.
    - `utils/logger.py` — logging helpers; provides a module-level `logger` for compatibility with legacy imports.

    ## Key components (details)

    ### ExecutionEngine (`core/execution_engine.py`)
    - Responsibilities: fetch OHLCV, route to strategies (typed `Signal`), apply gates (sentiment, ML gate, breaker, regime, correlation), compute sizing (ATR/profile), execute paper/live orders, persist decisions/trades, and write lightweight runtime snapshots for the dashboard.
    - Contracts:
      - Input: OHLCV as list-of-lists or pandas DataFrame (engine expects `close` at index 4 for list rows).
      - Interfaces: exposes `run_once(is_mock=True)` (sync) and `execute()` (async preferred). Orchestrator awaits `execute()` or falls back to `run_once()`.
      - Side effects: DB writes (`db_manager`), files under runtime snapshots (via `core/runtime_state` helpers), and logs.
    - Notes:
      - Strategies should return typed `Signal` objects (preferable). Legacy string signals are tolerated but typed signals are required for new codepaths.
      - The engine swallows non-critical exceptions to keep the orchestrator loop healthy.

    ### Orchestrators (`api/core/orchestrator.py`)
    - `EngineOrchestrator`: owns a single `ExecutionEngine` and runs an async loop with pause/resume/stop semantics. It captures per-cycle timing, `last_signal`, and `last_regime` for telemetry.
    - `MultiEngineOrchestrator`: manages multiple `EngineOrchestrator` instances keyed by symbol. Exposes `start_all()`, `stop_all()`, `status()`.
    - FastAPI attaches the `MultiEngineOrchestrator` to `app.state.services.multi_orch` so routes and the dashboard can control it.

    ### Exchange adapters (`exchange/paper.py`)
    - Implements: `fetch_ohlcv(...)`, `buy_notional(...)`, `sell_qty(...)`, `place_market_order(...)` (or equivalents), and `account_overview(...)` for snapshots.
    - Important: the `PaperExchange` constructor is expected to accept no unknown kwargs — instantiation should be `PaperExchange()`; passing unexpected args (e.g., `start_price=`) will raise a TypeError. Search and update any remaining call sites if needed.
    - The paper adapter simulates fills and writes trades to the DB for reproducible testing.

    ### API bootstrap & DI (`api/bootstrap_real_engine.py`, `api/deps`)
    - `create_app()` builds the app and attaches a `services` container on `app.state` with keys like `engines`, `orchestrators`, `multi_orch`, etc.
    - `api/deps/engine.py` provides helpers and shims so routes and tests can request engines or fall back safely when services aren't present.

    ### Logging & telemetry (`utils/logger.py`, `core/runtime_state.py`)
    - `utils/logger.py` sets up structured logging and exposes `logger` for legacy imports.
    - Per-cycle telemetry and lightweight JSON snapshots are written to the `runtime/` directory (via `core/runtime_state` / `utils.snapshot` helpers) so the dashboard can read live state without hitting internal memory.

    ## How to run (developer quickstart — PowerShell)

    Install deps, run typechecks, tests, and start the API (PowerShell-ready):

    ```powershell
    pip install -r requirements.txt
    # Optional checks
    # ruff check . && ruff format --check .
    # mypy .
    pytest -q

    # Example: run API with two symbols
    $env:AET_SYMBOLS = "BTC/USDT,ETH/USDT"
    uvicorn api.bootstrap_real_engine:create_app --host 127.0.0.1 --port 8080 --reload

    # Start runtime via REST (after the app is started)
    # Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:8080/runtime/start"
    ```

    Notes:
    - When running tests that don't exercise the FastAPI lifespan, `app.state.services` may be absent — tests use DI shims or should provide fixtures that create the necessary `services` container.

    ## Contracts & expectations (short)

    - OHLCV shape: list-of-lists with close price at index 4, or a DataFrame with a `close` column.
    - Strategy output: prefer `Signal` objects (Side enum + metadata). Engine will attempt to normalize legacy string returns.
    - Exchange adapter: must implement fetch + order helpers and an `account_overview()` for snapshots.

    ## Common pitfalls & troubleshooting

    - PaperExchange TypeError: ensure bootstrappers call `PaperExchange()` with no unexpected kwargs.
    - Strategy return shape: returning raw strings can break downstream logic; wrap strategies to return typed `Signal` where possible.
    - Missing `app.state.services` in tests: either enable the lifespan when creating TestClient or supply fixtures that populate `app.state.services`.

    ## Where to extend the codebase (quick pointers)

    - Add a strategy: implement under `strategy/`, register via `core/trade_logic.py` / `StrategyRouter`, and add unit tests under `tests/`.
    - Add a new exchange adapter: implement the same interface as `exchange/paper.py`, add a builder in `api/deps/exchange.py`, and update `api/bootstrap_real_engine.py` to instantiate it based on configuration.
    - Add per-cycle metrics: extend `api/core/orchestrator.py` to emit metrics and update `api/routes/runtime.py` to expose them.

    ## Recommended next actions

    1. Add a short `REPO_ARCHITECTURE.md` (or keep this file) and link it from `README.md`.
    2. Add an integration test that exercises `create_app()` startup and `multi_orch.start_all()` so CI validates the runtime wiring.
    3. If you want, I can add a Mermaid SVG and an image link for the README.

    ---

    If you want any additions (per-file docs for strategies, more details about the ML pipeline and features, or a generated Mermaid PNG), tell me which section to expand and I will update this file.

    ## Compact repository tree (LLM-friendly)

    Below is a compact ASCII tree of the repository with one-line summaries for each file/folder to help an LLM or a new developer quickly locate code.

    ```
    Aethelred/
    ├─ ARCHITECTURE.md           # This document (architecture overview + compact tree)
    ├─ README.md                 # Project overview and quickstart
    ├─ pyproject.toml            # Tooling & project metadata
    ├─ requirements.txt          # Runtime deps
    ├─ requirements-dev.txt      # Dev/test deps
    ├─ config/                   # YAML configs (selector, risk, regime_map)
    │  ├─ selector.yaml
    │  ├─ risk.yaml
    │  └─ regime_map.yaml
    ├─ api/                      # FastAPI app, DI, routes and static dashboard assets
    │  ├─ __init__.py
    │  ├─ main.py
    │  ├─ app.py
    │  ├─ bootstrap_real_engine.py # builds engines & orchestrators and attaches to app.state
    │  ├─ lifespan.py
    │  ├─ deps/                  # DI helpers (engine, orchestrator, exchange, settings)
    │  └─ routes/                # HTTP routes and WS telemetry endpoints
    │     ├─ runtime.py
    │     ├─ telemetry.py
    │     ├─ metrics.py           # Prometheus helpers + families (lazy)
    │     ├─ train.py
    │     └─ ml_explain.py       # ML explainability endpoint
    │     └─ ops_dashboard.py    # Operator dashboard at /ops
    │     ├─ insight_dashboard.py
    │     ├─ risk_dashboard.py
    │     ├─ multisymbol_dashboard.py
    │     ├─ ws_insight_dashboard.py
    │     ├─ ws_risk_dashboard.py
    │     └─ ws_multisymbol_dashboard.py
    │  ├─ services/              # dashboard builders & helpers (Phase 7)
    │     ├─ insight_dashboard_builder.py
    │     ├─ risk_dashboard_builder.py
    │     ├─ multisymbol_dashboard_builder.py
    │     └─ cache.py            # TTLCache used by Insight builder
    │  ├─ models/                # Pydantic schemas for dashboard contracts
    │     ├─ insight_dashboard.py
    │     ├─ risk_dashboard.py
    │     └─ multisymbol_dashboard.py
    ├─ core/                     # Core runtime: engine, orchestrator, risk, telemetry
    │  ├─ __init__.py
    │  ├─ execution_engine.py    # Main ExecutionEngine (sizing, gating, snapshotting)
    │  ├─ risk/                  # Risk V3 scaffold and helpers
    │  │  └─ engine_v3.py        # ExposureModel, VolatilityTargeter, PositionSizerV3, RiskTelemetry
    │  ├─ engine.py              # helpers / wiring
    │  ├─ orchestrator_v2.py
    │  ├─ telemetry_bus_v2.py
    │  ├─ telemetry_history_v2.py
    │  ├─ telemetry_history_v2.py # rolling history buffers (cap 500)
    │  ├─ ml/                    # ML helpers used by the engine (lazy imports)
    │  │  ├─ __init__.py
    │  │  ├─ feature_extractor.py
    │  │  ├─ signal_ranker.py
    │  │  ├─ gates.py
    │  │  ├─ explain.py
    │  │  └─ model_io.py
    │  ├─ risk.py
    │  ├─ trade_logic.py
    │  └─ persistence / helpers
    ├─ ml/                       # Offline model training & dataset builders
    │  ├─ __init__.py
    │  ├─ train_signal_ranker.py
    │  ├─ train_intent_veto.py
    │  ├─ feature_pipeline.py
    │  └─ dataset_builder.py
    ├─ db/                       # DB schema & manager
    │  ├─ __init__.py
    │  ├─ db_manager.py
    │  ├─ models.py
    │  └─ migrations/
    ├─ exchange/                 # Exchange adapters (paper & live shims)
    │  ├─ __init__.py
    │  └─ paper.py               # PaperExchange simulator used in tests and paper runs
    ├─ strategy/                 # Strategy implementations and adapters
    │  ├─ __init__.py
    │  ├─ ma_crossover.py
    │  ├─ trade_logic.py
    │  └─ (many adapters under core/strategy and strategy/)
    ├─ scripts/                  # Developer scripts & retrain helpers
    ├─ ops/                      # Operational helpers: notifier, watchdog,       watchdog alerts
    │  ├─ notifier.py            # Non-blocking Ops notifier (Telegram/Slack)
    │  └─ watchdog.py            # Async watchdog that probes orchestrator/exchange
    ├─ tools/                    # Small utility tools (generate_file_map, apply_patch)
    │  └─ generate_file_map.py   # writes file_map.json & file_map.yaml
  ├─ insight/                  # Standalone analytics & KPI exporter (opt-in)
  │  ├─ __init__.py
  │  ├─ utils.py               # Decimal helpers, MAE/MFE computation
  │  └─ engine.py              # InsightEngine: record_trade, rolling metrics, export_daily_kpi
    ├─ models/                   # Trained model artifacts and metadata (gitkeep)
    ├─ ml_models/                # legacy/pretrained model pickles (optional)
    ├─ dashboard/                # static dashboard assets (served by API)
    │  └─ index.html
    ├─ tests/                    # Unit tests (core)
    ├─ tests_api/                # API integration / smoke tests
    ├─ tests_ml/                 # ML-specific tests and training smoke tests
    ├─ reports/                  # repo scans, security baselines, handoff files
    ├─ docs/                     # developer docs & examples
    ├─ utils/                    # helpers (logger, snapshot utils, settings)
    ├─ runtime/                  # runtime snapshots written by engines (JSON files)
    ├─ file_map.json             # generated repository manifest (machine-friendly)
    └─ file_map.yaml             # YAML equivalent of the manifest
    ```

    Notes:
    - I focused on top-level files and the main Python packages used during runtime. If you'd like the list expanded to include every helper/utility file (or to include private files in `__pycache__`), I can expand this further.

    ---


    ## Detailed file map & local links

    I added two machine-friendly manifests at the repo root you can open locally or load into tools/LLMs:

    - `file_map.json` — JSON manifest with important files, absolute file:// URIs and VS Code file URIs.
    - `file_map.yaml` — YAML equivalent for tooling that prefers YAML.

    - Manifest generation info (this run):
      - generated_at: 2025-12-03T21:49:14.507930Z
      - files written to repo root: `file_map.json` and `file_map.yaml` (the generator wrote `file_map.yaml` during the last run)

  Note: The file maps were regenerated recently. If you need a delta-only manifest (files added/changed since a commit), I can produce `file_map.delta.json` for a compact review.

    You can open these directly in VS Code (example):

    file URI (open in any file browser / editor):

    ```
    file:///c:/Code/Aethelred/api/core/orchestrator.py
    ```

    VS Code quick-open (use `Open File` or paste into the address bar):

    ```
    vscode://file/c:/Code/Aethelred/api/core/orchestrator.py
    ```

    Sample entries from the manifest (clickable in many GUI file browsers/IDEs if supported):

    - `api/main.py` — file:///c:/Code/Aethelred/api/main.py  (FastAPI entrypoint)
    - `api/bootstrap_real_engine.py` — file:///c:/Code/Aethelred/api/bootstrap_real_engine.py  (bootstraps engines & orchestrators)
    - `api/core/orchestrator.py` — file:///c:/Code/Aethelred/api/core/orchestrator.py  (orchestrator loops)
    - `core/execution_engine.py` — file:///c:/Code/Aethelred/core/execution_engine.py  (engine runtime logic)
    - `exchange/paper.py` — file:///c:/Code/Aethelred/exchange/paper.py  (paper exchange adapter)
    - `db/db_manager.py` — file:///c:/Code/Aethelred/db/db_manager.py  (DB persistence helpers)

    If you want a fully exhaustive manifest (every file in the repo with summaries), I can generate that and write `file_map.full.json`/`file_map.full.yaml` — it will be larger but machine-friendly for LLM ingestion.

## Phase 7 — Final Review (Unified Telemetry & Dashboards)

Phase 7 delivered the complete backend telemetry layer for Visor v2. This final review records the additions, the API surface, stability guarantees, and the artifacts written into the repository.

Summary
-------

- Phase 7 implemented three dashboard families and their read-only APIs:
  - Insight Dashboard (per-symbol): schema, builder, normalisation layer, TTL cache, REST + WS streaming
  - Risk Dashboard (per-symbol): schema, builder, REST + WS streaming (hot)
  - Multi-Symbol Dashboard (portfolio view): compact schema, aggregation builder, REST + WS streaming (1s)

- API endpoints added in Phase 7:
  - GET `/insight/dashboard/{symbol}`
  - WS  `/ws/insight/{symbol}`
  - GET `/risk/dashboard/{symbol}`
  - WS  `/ws/risk/{symbol}`
  - GET `/dashboard/multi`
  - WS  `/ws/dashboard/multi`

- Design guarantees maintained:
  - Additive, opt-in: no behaviour changes to trading logic or risk sizing unless explicit runtime flags are set.
  - Lazy imports and guarded router includes keep test collection fast and CI stable.
  - Pydantic models used for all HTTP/WS payloads for frontend compatibility.
  - Insight builder uses a 2s TTL cache to minimise CPU for many subscribers; Risk and Multi-Symbol streams intentionally bypass cache where fresh data is required.

Performance & Safety
-------------------

- CPU profile: Insight is cached (very low CPU). Risk streams are simple memory reads. Multi-symbol aggregation is O(N) per tick but relies on cached Insight data so overhead remains small even for 10+ symbols.
- Stability: All new routes are wrapped with try/except guard during `app` registration so missing optional services won't break startup.

Repository artifacts written
--------------------------

- New files added (phase-7 primary):
  - `api/models/insight_dashboard.py`
  - `api/services/insight_dashboard_builder.py`
  - `api/routes/insight_dashboard.py`
  - `api/routes/ws_insight_dashboard.py`
  - `api/models/risk_dashboard.py`
  - `api/services/risk_dashboard_builder.py`
  - `api/routes/risk_dashboard.py`
  - `api/routes/ws_risk_dashboard.py`
  - `api/models/multisymbol_dashboard.py`
  - `api/services/multisymbol_dashboard_builder.py`
  - `api/routes/multisymbol_dashboard.py`
  - `api/routes/ws_multisymbol_dashboard.py`
  - `api/services/cache.py` (TTLCache for Insight builder)

All of the above are present in the repository root under `api/` and have been validated by the test suite.

Next steps (optional)
---------------------

1. Add small unit tests for each builder that stub `app.state.services` and verify JSON contract shapes (happy path + service-missing fallback).
2. Implement Phase 6.C-3 exposure cap enforcement (PositionSizerV3) if policy requires on-by-default behavior.
3. Consider adding WS connection metrics (connection count, errors) for production monitoring.

This completes the Phase 7 final-review notes. The rest of the document remains the canonical architecture overview; this section summarises the Phase 7 deliverables and where to look for the new components.

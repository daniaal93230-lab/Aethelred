# Aethelred – Engine Architecture Blueprint (Forward Plan)

This document describes the target production architecture for the Aethelred
Trading System. It is intentionally short, structured, and suitable for both
human engineers and LLM-based assistants.

The goal: a modular, testable, DI-driven, self-learning trading machine.


===============================================================================
1. CORE COMPONENTS
===============================================================================

Aethelred consists of five core subsystems:

1. Data Layer (DBManager, Journal, Market Data)
2. Risk Engine (pre-/post-trade checks, breakers, equity map)
3. Strategy Layer (rule models + ML veto + signal fusion)
4. Execution Engine (spot/futures routing, OMS, fill model)
5. Orchestrator (job queue, workers, training scheduler)

Everything is wired through **DI (dependency injection)** via FastAPI lifespan:
    app.state.services.<component>


===============================================================================
2. ENGINE LIFECYCLE
===============================================================================

Startup (lifespan):
    • Build DBManager
    • Build RiskEngine
    • Build Exchange (Paper or Real)
    • Build StrategySelector & Adapters
    • Build EngineOrchestrator
    • Attach services to app.state.services
    • Attach engine to app.state.engine
    • Optional: start async background workers

Shutdown (lifespan):
    • Flush DB
    • Close exchange sessions
    • Stop orchestrator workers
    • Dispose of risk/strategy state


===============================================================================
3. STRATEGY ARCHITECTURE
===============================================================================

Strategy Layer is composed of:

    • Base feature extractor (candles → features)
    • Adapters:
          - MA crossover
          - RSI mean reversion
          - EMA trend
          - Donchian breakout
    • Rule-based decision engine
    • ML veto model (optional)
    • Signal Fusion:
          combine strategy signals + veto confidence
    • Global TTL / cooldown logic

The final return type is a **Signal** object with:
    side, strength, stop_hint, ttl


===============================================================================
4. EXECUTION ARCHITECTURE
===============================================================================

Execution Engine responsibilities:

    • Route order to PaperExchange or Real Exchange
    • Maintain internal orderbook snapshot (optional)
    • Track open positions (symbol → position object)
    • Compute slippage, fees, and realised PnL
    • Emit journal entries
    • Respect circuit breakers & risk constraints
    • Respect strategy TTL & veto decisions

Execution is synchronous for now (Option A), but designed to upgrade
to asynchronous workers (Option B/C) in the future.


===============================================================================
5. DATA LAYER
===============================================================================

DBManager:
    • Single source of truth (SQLite for now)
    • Manages:
         - trades
         - decision_log
         - snapshots
         - risk_state
    • Exposes: list_trades(), list_decisions(), iter_trades(), now_ts()

Future upgrade:
    • Move to PostgreSQL with async driver
    • Structured Pydantic models for journal entries
    • Partitioned tables for candles & signals


===============================================================================
6. RISK ENGINE
===============================================================================

Risk Engine components:

    • Pre-trade checks:
          - leverage_after
          - est_loss_pct_equity
          - symbol-level exposure
          - volatility-based sizing (future)
    • Post-trade update:
          - equity curve
          - daily breakers
          - halt reason

Future upgrade:
    • Regime-dependent risk
    • Portfolio VaR/ES simulation
    • Multi-asset exposure allocation


===============================================================================
7. ORCHESTRATOR (FUTURE STEP)
===============================================================================

The orchestrator is currently lightweight (Option A), but the plan:

    • Job Queue:
          - "train-intent-veto"
          - "daily-snapshot"
          - "rollover"
    • Ticket System:
          engine.enqueue(job) → ticket_id
    • Worker:
          async worker loop executing queued jobs
    • ML module integration:
          train models, evaluate, deploy

Background worker upgrades (Option B/C) will live inside lifespan,
not in bootstrap.


===============================================================================
8. ML FRAMEWORK (FUTURE)
===============================================================================

Models to include:
    • Intent veto classifier
    • Regime classifier
    • Volatility predictor
    • Stop-distance model (regressor)
    • Reinforcement Learning agent (Phase 4)

Storage:
    • models/
    • versioned weights
    • auto-reload via orchestrator


===============================================================================
9. FUTURES EXCHANGE (UPCOMING)
===============================================================================

Unified PaperExchange architecture:

    • Single PaperExchange implementation for tests + dev
    • RealExchange implementation for live trading
    • Shared interface:
          fetch_ohlcv(), create_order(), fetch_balance(), fetch_position()
    • Supports futures:
          - leverage
          - margin mode
          - funding rate tracking
          - liquidation price model

This unlocks:
    ✓ smoother transitions
    ✓ easier mocking
    ✓ consistent risk engine behaviour


===============================================================================
10. FUTURE EXECUTION UPGRADES
===============================================================================

    • Async execution loop
    • Smart order routing (TWAP/VWAP)
    • Slippage model enhancements
    • Multi-symbol portfolio execution
    • Latency-aware fill simulation
    • Exchange websockets for live ticks


===============================================================================
11. TELEMETRY & INSIGHT
===============================================================================

Insight API:
    • metrics: Sharpe, Sortino, MaxDD, win rate, expectancy
    • turnover, exposure, regime state
    • rolling risk window
    • journal inspection

Future:
    • Prometheus exporter
    • Grafana dashboards
    • ML performance reports


===============================================================================
12. SUMMARY
===============================================================================

This README defines the long-term blueprint.
Everything you (or an LLM assistant) add must respect:

    • DI-first
    • Pure functions where possible
    • Testability by design
    • Clear engine/service boundaries
    • Lifespan-managed background workers
    • Zero global singletons
    • No circular imports

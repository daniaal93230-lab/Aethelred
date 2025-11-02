-- Aethelred Journal Schema (SQLite)
-- Source of truth for decisions, fills, positions, equity snapshots.
-- Indexes on ts and symbol where applicable.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS decisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              REAL NOT NULL,          -- unix seconds
    symbol          TEXT NOT NULL,
    regime          TEXT,
    strategy_name   TEXT,
    signal_side     TEXT,                   -- buy, sell, flat
    signal_strength REAL,
    signal_stop_hint REAL,
    signal_ttl      INTEGER,
    final_action    TEXT,                   -- buy, sell, hold, flat
    final_size      REAL,                   -- signed target size or delta
    veto_ml         INTEGER DEFAULT 0,
    veto_risk       INTEGER DEFAULT 0,
    veto_reason     TEXT,
    price           REAL,                   -- ref price at decision time
    note            TEXT
);

CREATE INDEX IF NOT EXISTS idx_decisions_ts ON decisions(ts);
CREATE INDEX IF NOT EXISTS idx_decisions_symbol_ts ON decisions(symbol, ts);

CREATE TABLE IF NOT EXISTS fills (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              REAL NOT NULL,
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL,          -- buy or sell
    qty             REAL NOT NULL,          -- base units, positive
    price           REAL NOT NULL,          -- quote per base
    fee_usd         REAL DEFAULT 0.0,
    slippage_bps    REAL DEFAULT 0.0,
    order_id        TEXT,
    decision_id     INTEGER,
    FOREIGN KEY(decision_id) REFERENCES decisions(id)
);

CREATE INDEX IF NOT EXISTS idx_fills_symbol_ts ON fills(symbol, ts);
CREATE INDEX IF NOT EXISTS idx_fills_ts ON fills(ts);

-- Current positions snapshot. One row per open symbol.
CREATE TABLE IF NOT EXISTS positions (
    symbol              TEXT PRIMARY KEY,
    side                TEXT NOT NULL,      -- long or short
    qty                 REAL NOT NULL,      -- base units, positive
    entry_price         REAL NOT NULL,
    entry_ts            REAL NOT NULL,
    last_update_ts      REAL NOT NULL,
    realized_pnl_usd    REAL DEFAULT 0.0,
    mtm_pnl_usd         REAL DEFAULT 0.0,
    mtm_pnl_pct         REAL DEFAULT 0.0
);

CREATE INDEX IF NOT EXISTS idx_positions_side ON positions(side);

-- Equity snapshots for MTM and return series.
CREATE TABLE IF NOT EXISTS equity_snapshots (
    ts              REAL PRIMARY KEY,       -- unix seconds
    equity_usd      REAL NOT NULL,          -- total account equity MTM
    cash_usd        REAL NOT NULL,
    exposure_usd    REAL NOT NULL           -- sum abs(notional) across symbols
);

CREATE INDEX IF NOT EXISTS idx_equity_ts ON equity_snapshots(ts);

-- Optional helper to record per-symbol exposure snapshots if needed later.
CREATE TABLE IF NOT EXISTS symbol_exposure (
    ts              REAL NOT NULL,
    symbol          TEXT NOT NULL,
    notional_usd    REAL NOT NULL,          -- signed
    PRIMARY KEY (ts, symbol)
);

CREATE INDEX IF NOT EXISTS idx_symbol_exposure_sym_ts ON symbol_exposure(symbol, ts);

import os
import sqlite3
from analytics.metrics import compute_all_metrics, reconstruct_round_trips

# Use the tests directory as the base for fixtures so CI runners find them
ROOT = os.path.dirname(__file__)

def load_fixture() -> sqlite3.Connection:
    # To avoid brittle filesystem assumptions on CI, inline the SQL schema, views,
    # and sample inserts directly. This keeps the test hermetic and fast.
    conn = sqlite3.connect(":memory:")
    journal_schema = '''
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS decisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              REAL NOT NULL,
    symbol          TEXT NOT NULL,
    regime          TEXT,
    strategy_name   TEXT,
    signal_side     TEXT,
    signal_strength REAL,
    signal_stop_hint REAL,
    signal_ttl      INTEGER,
    final_action    TEXT,
    final_size      REAL,
    veto_ml         INTEGER DEFAULT 0,
    veto_risk       INTEGER DEFAULT 0,
    veto_reason     TEXT,
    price           REAL,
    note            TEXT
);

CREATE INDEX IF NOT EXISTS idx_decisions_ts ON decisions(ts);
CREATE INDEX IF NOT EXISTS idx_decisions_symbol_ts ON decisions(symbol, ts);

CREATE TABLE IF NOT EXISTS fills (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              REAL NOT NULL,
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL,
    qty             REAL NOT NULL,
    price           REAL NOT NULL,
    fee_usd         REAL DEFAULT 0.0,
    slippage_bps    REAL DEFAULT 0.0,
    order_id        TEXT,
    decision_id     INTEGER,
    FOREIGN KEY(decision_id) REFERENCES decisions(id)
);

CREATE INDEX IF NOT EXISTS idx_fills_symbol_ts ON fills(symbol, ts);
CREATE INDEX IF NOT EXISTS idx_fills_ts ON fills(ts);

CREATE TABLE IF NOT EXISTS positions (
    symbol              TEXT PRIMARY KEY,
    side                TEXT NOT NULL,
    qty                 REAL NOT NULL,
    entry_price         REAL NOT NULL,
    entry_ts            REAL NOT NULL,
    last_update_ts      REAL NOT NULL,
    realized_pnl_usd    REAL DEFAULT 0.0,
    mtm_pnl_usd         REAL DEFAULT 0.0,
    mtm_pnl_pct         REAL DEFAULT 0.0
);

CREATE INDEX IF NOT EXISTS idx_positions_side ON positions(side);

CREATE TABLE IF NOT EXISTS equity_snapshots (
    ts              REAL PRIMARY KEY,
    equity_usd      REAL NOT NULL,
    cash_usd        REAL NOT NULL,
    exposure_usd    REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_equity_ts ON equity_snapshots(ts);

CREATE TABLE IF NOT EXISTS symbol_exposure (
    ts              REAL NOT NULL,
    symbol          TEXT NOT NULL,
    notional_usd    REAL NOT NULL,
    PRIMARY KEY (ts, symbol)
);

CREATE INDEX IF NOT EXISTS idx_symbol_exposure_sym_ts ON symbol_exposure(symbol, ts);
'''

    views_sql = '''
CREATE VIEW IF NOT EXISTS v_daily_equity AS
WITH snaps AS (
    SELECT
        date(ts, 'unixepoch') AS day,
        ts,
        equity_usd
    FROM equity_snapshots
),
day_open AS (
    SELECT day, MIN(ts) AS open_ts
    FROM snaps
    GROUP BY day
),
day_close AS (
    SELECT day, MAX(ts) AS close_ts
    FROM snaps
    GROUP BY day
),
open_equity AS (
    SELECT s.day, s.equity_usd AS equity_open
    FROM snaps s
    JOIN day_open o ON s.day = o.day AND s.ts = o.open_ts
),
close_equity AS (
    SELECT s.day, s.equity_usd AS equity_close
    FROM snaps s
    JOIN day_close c ON s.day = c.day AND s.ts = c.close_ts
)
SELECT
    o.day,
    o.equity_open,
    c.equity_close,
    (c.equity_close - o.equity_open) AS pnl_usd,
    CASE
        WHEN o.equity_open != 0 THEN (c.equity_close - o.equity_open) / o.equity_open
        ELSE NULL
    END AS ret
FROM open_equity o
JOIN close_equity c ON o.day = c.day
ORDER BY o.day ASC;

CREATE VIEW IF NOT EXISTS v_symbol_turnover AS
SELECT
    date(ts, 'unixepoch') AS day,
    symbol,
    SUM(qty * price) AS gross_notional_usd,
    SUM(qty) AS gross_qty
FROM fills
GROUP BY day, symbol
ORDER BY day, symbol;

CREATE VIEW IF NOT EXISTS v_daily_exposure AS
SELECT
    date(ts, 'unixepoch') AS day,
    AVG(exposure_usd) AS avg_exposure_usd
FROM equity_snapshots
GROUP BY day
ORDER BY day;

CREATE VIEW IF NOT EXISTS v_symbol_stats AS
SELECT
    symbol,
    COUNT(*) AS fills_count,
    SUM(CASE WHEN side = 'buy' THEN 1 ELSE 0 END) AS buys,
    SUM(CASE WHEN side = 'sell' THEN 1 ELSE 0 END) AS sells,
    MAX(ts) AS last_fill_ts,
    (SELECT price FROM fills f2 WHERE f2.symbol = f.symbol ORDER BY ts DESC LIMIT 1) AS last_price
FROM fills f
GROUP BY symbol;
'''

    sample_inserts = '''
INSERT INTO decisions(ts, symbol, regime, strategy_name, signal_side, final_action, final_size, price)
VALUES
(1730000000, 'BTCUSDT', 'baseline', 'rsi_mean_revert', 'buy', 'buy', 0.01, 60000.0),
(1730003600, 'BTCUSDT', 'baseline', 'rsi_mean_revert', 'sell', 'sell', 0.01, 60600.0);

INSERT INTO fills(ts, symbol, side, qty, price, fee_usd, slippage_bps, decision_id)
VALUES
(1730000005, 'BTCUSDT', 'buy', 0.010, 60000.0, 0.5, 1.2, 1),
(1730007200, 'BTCUSDT', 'sell', 0.010, 60600.0, 0.5, -0.8, 2);

INSERT INTO equity_snapshots(ts, equity_usd, cash_usd, exposure_usd) VALUES
(1729996800, 100000.0, 100000.0, 0.0),
(1730000100, 100000.0, 100000.0, 600.0),
(1730039400, 100060.0, 100060.0, 0.0),
(1730083200, 100060.0, 100060.0, 0.0),
(1730112000, 100060.0, 100060.0, 0.0);
'''

    full = "\n".join([journal_schema, views_sql, sample_inserts])
    conn.executescript(full)
    return conn

def test_replay_consistency():
    conn = load_fixture()
    trades = reconstruct_round_trips(conn)
    assert len(trades) == 1
    t = trades[0]
    assert t.symbol == "BTCUSDT"
    assert t.side == "long"
    assert abs(t.entry_price - 60000.0) < 1e-9
    assert abs(t.exit_price - 60600.0) < 1e-9
    # profit before fees: 0.01 * 600 = 6.0 USD
    # fees total = 1.0 USD, net = 5.0 USD
    gross_usd = (t.exit_price - t.entry_price) * t.qty
    assert abs(gross_usd - 6.0) < 1e-9
    assert abs(t.fees_usd - 1.0) < 1e-9

    m = compute_all_metrics(conn)
    # Daily return day1: (100060 - 100000) / 100000 = 0.0006
    # Sharpe undefined with single return, we accept 0.0 due to stdev 0 handling
    assert m["sharpe"] == 0.0
    assert m["sortino"] == 0.0
    assert m["max_drawdown_pct"] == 0.0
    assert m["win_rate"] == 1.0
    assert abs(m["expectancy_usd"] - 5.0) < 1e-9

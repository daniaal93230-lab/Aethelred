-- Views for daily PnL, per-symbol stats, and helper series

-- Daily equity rollup with day-level PnL and return
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

-- Per-symbol turnover and gross notional traded per day
CREATE VIEW IF NOT EXISTS v_symbol_turnover AS
SELECT
    date(ts, 'unixepoch') AS day,
    symbol,
    SUM(qty * price) AS gross_notional_usd,
    SUM(qty) AS gross_qty
FROM fills
GROUP BY day, symbol
ORDER BY day, symbol;

-- Helper: exposure by day from equity snapshots if symbol_exposure exists
CREATE VIEW IF NOT EXISTS v_daily_exposure AS
SELECT
    date(ts, 'unixepoch') AS day,
    AVG(exposure_usd) AS avg_exposure_usd
FROM equity_snapshots
GROUP BY day
ORDER BY day;

-- Per-symbol simple stats from fills only (counts, last price)
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

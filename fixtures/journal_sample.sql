.read db/journal_schema.sql
.read db/views_journal.sql

-- Decisions (optional linkage)
INSERT INTO decisions(ts, symbol, regime, strategy_name, signal_side, final_action, final_size, price)
VALUES
(1730000000, 'BTCUSDT', 'baseline', 'rsi_mean_revert', 'buy', 'buy', 0.01, 60000.0),
(1730003600, 'BTCUSDT', 'baseline', 'rsi_mean_revert', 'sell', 'sell', 0.01, 60600.0);

-- Fills forming a long round-trip
INSERT INTO fills(ts, symbol, side, qty, price, fee_usd, slippage_bps, decision_id)
VALUES
(1730000005, 'BTCUSDT', 'buy', 0.010, 60000.0, 0.5, 1.2, 1),
(1730007200, 'BTCUSDT', 'sell', 0.010, 60600.0, 0.5, -0.8, 2);

-- Equity snapshots across 2 days
INSERT INTO equity_snapshots(ts, equity_usd, cash_usd, exposure_usd) VALUES
(1729996800, 100000.0, 100000.0, 0.0),      -- day 1 open 00:00 UTC
(1730000100, 100000.0, 100000.0, 600.0),    -- after entry small exposure proxy
(1730039400, 100060.0, 100060.0, 0.0),      -- day 1 close (profit)
(1730083200, 100060.0, 100060.0, 0.0),      -- day 2 open
(1730112000, 100060.0, 100060.0, 0.0);      -- day 2 close

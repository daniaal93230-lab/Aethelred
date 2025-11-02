-- Example SQL views for realized pnl and trade count today
-- Adapt table and column names to your schema
-- Assumes a 'trades' table with columns: ts_close (UTC seconds), pnl_usd numeric

CREATE OR REPLACE VIEW v_realized_pnl_today_usd AS
SELECT
  COALESCE(SUM(pnl_usd), 0.0) AS realized_pnl_today_usd
FROM trades
WHERE ts_close >= EXTRACT(EPOCH FROM date_trunc('day', now() AT TIME ZONE 'UTC'));

CREATE OR REPLACE VIEW v_trade_count_today AS
SELECT
  COUNT(*) AS trade_count_today
FROM trades
WHERE ts_close >= EXTRACT(EPOCH FROM date_trunc('day', now() AT TIME ZONE 'UTC'));

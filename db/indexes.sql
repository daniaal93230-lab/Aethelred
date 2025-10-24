-- Optional indexes to speed up exports and dashboards
-- Adapted to Aethelred schema

create index if not exists idx_paper_trades_ts on paper_trades(ts);
create index if not exists idx_decision_log_symbol_ts on decision_log(symbol, ts);
create index if not exists idx_equity_snapshots_ts on equity_snapshots(ts);

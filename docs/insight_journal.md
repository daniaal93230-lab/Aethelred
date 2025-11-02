# Aethelred Insight Journal and Metrics

## Tables

Defined in `db/journal_schema.sql`:

- `decisions`: canonical decision log aligned with `api/contracts/decisions_header.py`.
- `fills`: executed fills with optional `decision_id` FK to link fills back to decisions.
- `positions`: current open positions snapshot per symbol.
- `equity_snapshots`: MTM equity, cash, and exposure snapshots for performance truth.
- `symbol_exposure`: optional per-symbol notional snapshots if needed later.

All time series tables indexed by `ts` and `(symbol, ts)` where applicable.

## Views

Defined in `db/views_journal.sql`:

- `v_daily_equity`: day open and close equity with `pnl_usd` and `ret`.
- `v_symbol_turnover`: daily gross notional and qty by symbol.
- `v_daily_exposure`: daily average exposure from snapshots.
- `v_symbol_stats`: quick symbol activity stats from fills.

## Metrics functions

Implemented in `analytics/metrics.py` using only stdlib and SQLite:

- `sharpe`, `sortino` on daily returns from `v_daily_equity`.
- `max_drawdown_from_equity` on daily closing equity.
- `reconstruct_round_trips` builds flat-to-flat trades per symbol from `fills`.
- `win_rate_and_expectancy` from reconstructed trades, net of fees.
- `average_exposure_and_turnover` from snapshots and `v_symbol_turnover`.
- `compute_all_metrics` returns a compact dict for orchestrator checks.

## Daily PnL and per symbol stats

Defined in `db/views_journal.sql`:

```sql
-- Daily PnL and returns
SELECT day, pnl_usd, ret FROM v_daily_equity ORDER BY day;

-- Per-symbol turnover
SELECT * FROM v_symbol_turnover WHERE day >= date('now','-14 day') ORDER BY day, symbol;

-- Quick symbol stats
SELECT * FROM v_symbol_stats ORDER BY symbol;
```

## trades.csv export contract

Defined in `api/contracts/trades_header.py` as `TRADES_HEADER`. The API exporter or CLI must emit the header exactly, in the same order:

```
trade_id,symbol,side,qty,entry_ts,exit_ts,entry_price,exit_price,pnl_usd,pnl_pct,hold_seconds,fees_usd,slippage_bps,decision_id,strategy_name,regime,note
```

Field rules:

- `trade_id`: stable integer from DB.
- `side`: `long` or `short`.
- `qty`: positive base quantity for the round-trip.
- `pnl_usd`: realized PnL net of fees.
- `pnl_pct`: realized PnL divided by signed entry notional.
- `hold_seconds`: exit_ts - entry_ts.
- `decision_id`, `strategy_name`, `regime` are optional denormalized helpers for joins.

## Testing

`tests/test_metrics_replay_consistency.py` loads `tests/fixtures/journal_sample.sql` into an in-memory SQLite DB and asserts:

- Round-trip reconstruction yields a single trade with expected PnL.
- Metrics dictionary is consistent on the sample replay.

## Success criteria

- With real snapshots and fills, `analytics/metrics.compute_all_metrics` produces stable numbers for the orchestrator.
- `TRADES_HEADER` is used by the API exporter. If engine field names differ, perform mapping at the exporter boundary.

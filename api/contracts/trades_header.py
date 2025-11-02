"""
Canonical header for trades.csv that the API must serve.
Keep this the single source of truth for downstream consumers.
"""

# Order of columns is contractually significant.
TRADES_HEADER = [
    "trade_id",  # stable unique id within DB
    "symbol",
    "side",  # long or short
    "qty",  # base units, positive
    "entry_ts",  # unix ts seconds (float allowed)
    "exit_ts",  # unix ts seconds (float allowed)
    "entry_price",  # in quote currency
    "exit_price",  # in quote currency
    "pnl_usd",  # realized PnL in USD
    "pnl_pct",  # realized PnL as pct of entry notional signed
    "hold_seconds",
    "fees_usd",  # total fees across legs
    "slippage_bps",  # signed avg slippage vs signal or mid
    "decision_id",  # foreign key to decisions.id when available
    "strategy_name",  # denormalized for convenience
    "regime",  # denormalized for convenience
    "note",  # free text if any
]

# Minimal types hint for exporters and validators.
TRADES_DTYPES = {
    "trade_id": "int",
    "symbol": "str",
    "side": "str",
    "qty": "float",
    "entry_ts": "float",
    "exit_ts": "float",
    "entry_price": "float",
    "exit_price": "float",
    "pnl_usd": "float",
    "pnl_pct": "float",
    "hold_seconds": "float",
    "fees_usd": "float",
    "slippage_bps": "float",
    "decision_id": "int?",
    "strategy_name": "str?",
    "regime": "str?",
    "note": "str?",
}

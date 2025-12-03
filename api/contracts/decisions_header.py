# api/contracts/decisions_header.py
# Canonical decisions header required by the test-suite.
# Order is STRICT — do not reorder or rename.

DECISIONS_HEADER = [
    "ts",
    "symbol",
    "regime",
    "strategy_name",
    "signal_side",
    "signal_strength",
    "signal_stop_hint",
    "signal_ttl",
    "final_action",
    "final_size",
    "veto_ml",
    "veto_risk",
    "veto_reason",
    "price",
    "note",
]

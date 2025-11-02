# Strategos: Strategy Interface and Raw Signal Logging

## Interface
Implement:

```python
class Strategy(Protocol):
    name: str
    def prepare(self, ctx: Dict[str, Any]) -> None: ...
    def generate_signal(self, market_state: Dict[str, Any]) -> Signal: ...
```

`market_state` is a dict of numpy arrays:
- "o","h","l","c","v" as 1D arrays. No I/O. No sizing. No vetoes.

`Signal` fields:
- side: "BUY" | "SELL" | "HOLD"
- strength: float in [0, 1]
- stop_hint: price or None
- ttl: bars to keep the signal valid

Give your class a stable `name` string, for example:
- `ma_crossover`, `rsi_mean_revert`, `donchian_breakout`

## Raw signal logging
The engine emits a canonical row per bar before ML veto and risk:

Fields are defined in `api/contracts/decisions_header.py` and exported by `/export/decisions.csv`:

```
ts, symbol, regime, strategy_name,
signal_side, signal_strength, signal_stop_hint, signal_ttl,
final_action, final_size, veto_ml, veto_risk, veto_reason, price, note
```

If the runtime logs in two stages, exporter coalesces rows by `(ts, symbol)` keeping last non-null of the final_* and veto_* fields.


## Selector
Use `StrategySelector` to pick one strategy per symbol per regime. Unknown regimes fall back safely. Register overrides as needed.

### Declarative regime map
Place an environment-keyed YAML at `config/regime_map.yaml`:
```yaml
default_env: "prod"
envs:
    prod:
        default_strategy: "ma_crossover"
        overrides:
            BTCUSDT: "ma_crossover"
            ETHUSDT: "rsi_mean_revert"
            SOLUSDT: "donchian_breakout"
    paper:
        default_strategy: "rsi_mean_revert"
        overrides: {}
```
At init the engine reads env `AETHELRED_ENV` (default prod), loads the map, and for each symbol picks the named strategy through the selector. No code edits needed to change choices.

### Schema for ML consumers
`/export/decisions.schema.json` serves a JSON Schema that mirrors `DECISIONS_HEADER`. Consumers can validate that CSVs include and type fields correctly.

## Tests
Add deterministic tests on canned OHLCV. Avoid I/O. Keep calculations pure.

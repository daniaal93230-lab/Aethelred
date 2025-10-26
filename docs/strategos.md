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
Place a YAML file at `config/selector.yaml`:
```yaml
defaults:
    regime: trending
overrides:
    BTCUSDT: trending
    ETHUSDT: mean_revert
    SOLUSDT: breakout
```
The engine loads this on init, setting `engine.symbol_regime_default` and `engine.symbol_regime`. During the sweep it uses
`symbol_regime.get(symbol, symbol_regime_default)` to select a strategy via the selector.

## Tests
Add deterministic tests on canned OHLCV. Avoid I/O. Keep calculations pure.

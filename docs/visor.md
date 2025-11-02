# Aethelred Visor

Minimal UI for truth. Two panels and a status row.

## Run

```bash
pip install -e ".[visor]"
./scripts/run_visor.sh http://127.0.0.1:8080 2
```

On Windows:

```powershell
pip install -e .[visor]
scripts\run_visor.ps1 -ApiBase "http://127.0.0.1:8080" -RefreshSecs 2
```

## What it reads
- `GET /healthz` for breaker and kill switch hints
- `GET /runtime/account_runtime.json` for heartbeat, equity series, and open positions

Both endpoints are configurable by VISOR_API_BASE env var.

## Signals at a glance
- Breaker chip shows status, kill switch, and daily breaker state
- Equity chart shows recent equity over time
- Open positions table shows symbol, side, qty, entry, mark, PnL%

## Env
- `VISOR_API_BASE` default `http://127.0.0.1:8080`
- `VISOR_REFRESH_SECS` default `2`
- `VISOR_HTTP_TIMEOUT` default `2.5`

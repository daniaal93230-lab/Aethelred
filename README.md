# Aethelred

Trading research and paper-trading stack with simple FastAPI endpoints, risk controls, and lightweight ML.

## Cleanup and structure

We are consolidating to a single execution path and removing legacy, duplicate, or superseded modules.
Run the prune script once after this patch:

```bash
python scripts/prune_legacy.py --apply
```

If you want a dry run first:

```bash
python scripts/prune_legacy.py --dry-run
```

After pruning, use the unified runner:

```bash
python run.py --mode paper   # or --mode live
```

LLM-friendly quickstart
This repo includes small helpers to make analysis easier for tools and LLMs:


To generate a compact machine-friendly index of the repo:

```powershell
python scripts/generate_repo_index.py
```

Then open `repo_index.json` to see files, docstrings and first lines.

## Models
Calibrated intent veto (Platt scaling) can be trained via API or the included script.

API example:

```bash
curl -X POST http://127.0.0.1:8080/train \
	-H "content-type: application/json" \
	-d '{"signals_csv":"data/decisions.csv","candles_csv":"data/candles/BTCUSDT.csv","horizon":12,"symbol":"BTCUSDT"}'
```

CLI example (dev script):

```bash
./scripts/train_intent_veto.sh
```

Artifacts are written to `models/intent_veto/model.pkl` and `model_meta.json` with the tuned decision threshold and validation ECE.

## Testing
Run the test suite:

```bash
pytest -q
```

To run only the ML suite:

```bash
pytest -q tests_ml
```

## Start API with real engine

```powershell
setx LIVE 1
rem Example Postgres DSN
setx DB_URL "postgres://user:pass@localhost:5432/aethelred"
rem Run migrations once
python scripts/run_migrations.py
uvicorn api.bootstrap_real_engine:create_app --host 127.0.0.1 --port 8080 --reload
```

Health returns positions_count and last_tick_ts. The watchdog can be run with:
`python scripts/watchdog.py --base http://127.0.0.1:8080 --interval 2 --failures 2`

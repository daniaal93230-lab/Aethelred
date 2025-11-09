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

## Architecture summary (LLM-friendly)

Short, structured summary useful for fast onboarding or prompting an assistant:

- Language: Python 3.11+; main entry points in `api/` and `bot/`.
- API: FastAPI app under `api/main.py` exposing health/runtime endpoints used by Visor.
- Engine: trading engine objects live under `bot/brain.py` and `core/engine.py` (look for `account_snapshot()` and `runtime_snapshot`).
- Persistence: sqlite (`data/ledger.db`) for quick dev; code also supports DB_URL env for Postgres.
- Scripts: `tools/` contains dev helpers (start/stop scripts, diagnostics), `scripts/` contains maintenance tasks.
- Watchdog/Visor: `tools/start_paper.ps1` launches uvicorn + watchdog + visor (streamlit) for QA runs.

Recommended quick prompts for an assistant:

- "Where is the FastAPI app defined?" -> `api/main.py`
- "How does the engine expose runtime state?" -> look for `account_snapshot()` in `bot/brain.py` and `core/runtime_state` persistence.
- "Where are dev scripts to start the API and Visor?" -> `tools/start_paper.ps1`

## Port / HTTP.SYS troubleshooting (dev machines)

Problem we encountered: on Windows a kernel-owned binding (HTTP.SYS) can claim `127.0.0.1:8080` and present as `[System]` in `netstat -abno`, preventing uvicorn from binding. This is typically resolved by one of:

- identifying and stopping the Windows service that registered the URL (via `Get-CimInstance Win32_Service`),
- removing a URL ACL (`netsh http delete urlacl url="http://+:8080/"`) — only if you own that reservation,
- running the non-destructive diagnostics helper: `tools/port_guard.ps1 -Port 8080` (Admin recommended). It collects netstat, netsh and process info and optionally downloads Sysinternals tools for deeper inspection.
- reboot (clears kernel registrations) as a last resort on dev machines.

How to use the helper (Admin recommended):

```powershell
# produces a report under %TEMP%/port_guard_<port>/report.txt and opens it in Notepad
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\port_guard.ps1 -Port 8080 -IncludeSysinternals
```

Only delete URL ACLs or stop services you understand. The helper is intentionally non-destructive and meant to collect evidence to safely fix the reservation.

## Developer checks (quick)

Run the dev checks used by CI locally before pushing:

```powershell
# install deps (from workspace task)
powershell -Command "& { .venv\Scripts\pip.exe install -r requirements.txt }"

# lint + format check
powershell -Command "& { ruff check . && ruff format --check . }"

# typecheck
powershell -Command "& { mypy . }"

# tests
powershell -Command "& { pytest -q }"
```

If tests fail, run `pytest -q -k <testname>` and paste failures; the repo aims to keep a green test suite.


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

### Paper-session retraining

When `data/decisions.csv` and `data/trades.csv` exist, the `/train` endpoint will automatically derive labels from realized trade outcomes, perform balanced LogisticRegression + CalibratedClassifierCV, and tune threshold by ECE.

**Acceptance targets:**
- ECE < 3 % on validation
- Balanced precision/recall
- Artifacts written under `models/intent_veto/`
- `core/ml_gate.py` logs `model_version` and uses tuned threshold at runtime

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

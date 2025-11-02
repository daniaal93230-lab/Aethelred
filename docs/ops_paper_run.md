# Supervised paper session runbook

## One-liner (Windows)
```
scripts\run_api_paper.ps1
```

## One-liner (Linux/macOS)
```
chmod +x scripts/run_api_paper.sh
scripts/run_api_paper.sh
```

This will:
1) export `MODE=paper`, `SAFE_FLATTEN_ON_START=1`, `QA_DEV_ENGINE=1`
2) start the API on `:8080`
3) run `watchdog.py`
4) POST `/demo/paper_quick_run`

Verify:
- `GET /healthz` -> engine attached
- `GET /export/decisions.csv` and `/export/trades.csv`
- Visor: `VISOR_API_BASE=http://127.0.0.1:8080 streamlit run apps/visor/streamlit_app.py`

> Legacy note: `scripts/run_paper_loop.ps1` used the old `bot/` stack and is deprecated.

#!/usr/bin/env bash
set -euo pipefail
API_BASE="${1:-http://127.0.0.1:8080}"

export MODE=paper
export SAFE_FLATTEN_ON_START=1
export QA_DEV_ENGINE=1

echo "Starting API on :8080 (MODE=$MODE QA_DEV_ENGINE=$QA_DEV_ENGINE)..."
uvicorn api.main:app --host 127.0.0.1 --port 8080 --reload &
API_PID=$!
sleep 2

echo "Starting watchdog..."
python scripts/watchdog.py --base "$API_BASE" --interval 2 --failures 2 &
sleep 1

echo "Kick demo /demo/paper_quick_run..."
curl -sS -X POST "$API_BASE/demo/paper_quick_run" -H "content-type: application/json" -d '{}' || true

echo "Visor tip: VISOR_API_BASE=$API_BASE streamlit run apps/visor/streamlit_app.py"
wait $API_PID

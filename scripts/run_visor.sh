#!/usr/bin/env bash
set -euo pipefail

API_BASE="${1:-http://127.0.0.1:8080}"
REFRESH_SECS="${2:-2}"

export VISOR_API_BASE="$API_BASE"
export VISOR_REFRESH_SECS="$REFRESH_SECS"

echo "Starting Visor against ${VISOR_API_BASE} refresh ${VISOR_REFRESH_SECS}s"
python -m streamlit run apps/visor/streamlit_app.py

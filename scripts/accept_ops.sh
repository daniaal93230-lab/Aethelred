#!/usr/bin/env bash
set -euo pipefail
BASE="${1:-http://127.0.0.1:8080}"

echo "Start engine in another terminal, then press enter"
read -r

echo "1) Open test position"
curl -sS -X POST "$BASE/order/market" -H 'Content-Type: application/json' \
  -d '{"symbol":"BTCUSDT","side":"buy","qty":0.001}' >/dev/null

echo "2) Health"
curl -sS "$BASE/healthz" | jq .

echo "3) Start watchdog"
python scripts/watchdog.py --base "$BASE" --interval 2 --failures 2 >/tmp/watchdog.log 2>&1 &
WD_PID=$!
echo "watchdog pid=$WD_PID"

echo "4) Simulate crash. Adjust process name to your runner"
pkill -f "aethelred.*runner" || true
sleep 5

echo "5) Positions after watchdog flatten"
curl -sS "$BASE/metrics_json" | jq .

echo "6) Runtime snapshot"
cat account_runtime.json || true

kill $WD_PID || true

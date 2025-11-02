#!/usr/bin/env bash
set -euo pipefail
python -m ml.train_intent_veto \
  --signals data/decisions.csv \
  --candles data/candles/BTCUSDT.csv \
  --out models/intent_veto \
  --h 12 \
  --symbol BTCUSDT

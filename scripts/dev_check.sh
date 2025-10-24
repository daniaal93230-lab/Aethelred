#!/usr/bin/env bash
set -euo pipefail
ruff check api tests_api
mypy api tests_api
pytest -q
echo "OK"

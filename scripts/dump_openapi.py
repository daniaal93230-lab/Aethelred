"""Dump the FastAPI app OpenAPI JSON to `api/openapi.json`.

This imports the FastAPI app from `api.main` and writes `app.openapi()` to file.
"""

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
# Ensure repo root on sys.path so `api` is importable when run from scripts/
sys.path.insert(0, str(ROOT))
OUT = ROOT / "api" / "openapi.json"

try:
    # try import app from api.main
    from api.main import app  # type: ignore

    spec = app.openapi()
    if spec is None:
        spec = {}
    OUT.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}")
except Exception as e:
    print(f"Failed to dump OpenAPI: {e}")

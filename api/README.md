API module

FastAPI application and HTTP routes.

Key files:
- `api/main.py` — FastAPI app factory and router registration.
- `api/routes/export.py` — CSV/JSONL exporters for trades and decisions.
- `api/contracts/decisions_header.py` — canonical header for decisions exports.

Use `uvicorn api.main:app --reload --port 8080` to run locally. The `scripts/list_routes.py` helper prints registered routes.

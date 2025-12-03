# api/app.py

"""
Aethelred FastAPI Application Factory
-------------------------------------
Loads the app, attaches lifespan logic, and registers routes.

Batch 6A-2: lifespan now handles orchestrator startup/shutdown.

All heavy initialization is executed in `api.lifespan`.
"""

from fastapi import FastAPI
from api.lifespan import lifespan
from api.routes import router as api_router
from api.routes.health import router as health_router
from api.routes.export import router as export_router
from api.routes.ops_dashboard import router as ops_dashboard_router
from api.routes.risk import router as risk_router
from api.routes.insight import router as insight_router
from api.routes.insight_dashboard import router as insight_dashboard_router
from api.routes import ws_insight_dashboard
from api.routes import risk_dashboard
from api.routes import multisymbol_dashboard
from api.routes import ws_multisymbol_dashboard
from api.routes import ws_risk_dashboard
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import os


def create_app() -> FastAPI:
    """
    App factory with clean lifespan + router loading.
    """
    app = FastAPI(
        title="Aethelred Trading API",
        version="1.0.0",
        lifespan=lifespan,
    )

    # /health (always first)
    app.include_router(health_router)
    # Main API routes
    app.include_router(api_router)
    # Export routes (required for test suite)
    app.include_router(export_router, prefix="/export")
    # Ops dashboard
    app.include_router(ops_dashboard_router)
    # Risk telemetry endpoint (Phase 6.D-1)
    try:
        app.include_router(risk_router)
    except Exception:
        pass

    # Insight routes (Phase 6.E-5)
    try:
        app.include_router(insight_router)
    except Exception:
        pass

    # Insight dashboard route (7.A-4)
    try:
        app.include_router(insight_dashboard_router)
    except Exception:
        app.include_router(risk_dashboard.router)
        pass

    # Insight dashboard websocket (7.A-7)
    try:
        app.include_router(ws_insight_dashboard.router)
    except Exception:
        pass

    # Multi-symbol dashboard (7.C-3)
    try:
        app.include_router(multisymbol_dashboard.router)
    except Exception:
        pass

    # Risk dashboard websocket (7.B-4)
    try:
        app.include_router(ws_risk_dashboard.router)
    except Exception:
        pass

    # Multi-symbol dashboard websocket (7.C-4)
    try:
        app.include_router(ws_multisymbol_dashboard.router)
    except Exception:
        pass

    # Serve dashboard static assets
    static_path = os.path.join(os.path.dirname(__file__), "static")
    if os.path.isdir(static_path):
        app.mount("/static", StaticFiles(directory=static_path), name="static")

        # Dashboard HTML
        @app.get("/dashboard", response_class=HTMLResponse)
        async def dashboard_html():
            with open(os.path.join(static_path, "dashboard.html"), "r", encoding="utf-8") as f:
                return f.read()

    return app


# CLI execution / uvicorn entrypoint
app = create_app()

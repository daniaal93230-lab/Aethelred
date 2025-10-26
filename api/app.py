from fastapi import FastAPI
from api.routes import router as root_router

app = FastAPI(title="Aethelred API")
app.include_router(root_router)


# Optional cycle hook for orchestration code that imports make_app()
def on_cycle_complete():
    try:
        from utils.snapshot import write_runtime_snapshot
        from .main import app

        write_runtime_snapshot(app.state.engine)
    except Exception:
        pass

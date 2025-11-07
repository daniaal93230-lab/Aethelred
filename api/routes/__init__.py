from fastapi import APIRouter
from .risk import router as risk_router
from .ops import router as ops_router
from .demo import router as demo_router
from .ui import router as ui_router
from .export import router as export_router
from utils.settings import qa_mode
from .runtime import router as runtime_router
from .demo_loop import router as demo_loop_router


router = APIRouter()
router.include_router(risk_router)
router.include_router(ops_router)
router.include_router(demo_router)
router.include_router(ui_router)
router.include_router(export_router, prefix="/export")
# Runtime JSON for Visor
router.include_router(runtime_router, tags=["runtime"])
router.include_router(demo_loop_router, tags=["demo"])
if qa_mode():
    from .qa_sim import router as qa_router

    router.include_router(qa_router)

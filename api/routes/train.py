from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()


class TrainRequest(BaseModel):
    job: str = "default"
    notes: str | None = None


@router.post("/train")
async def trigger_train(req: TrainRequest, request: Request):
    """
    Thin trigger for ML training. No training logic here.
    Delegates to engine.orchestrator which enqueues work or signals a worker.
    Idempotent: repeated calls with the same job key should be safe.
    """
    eng = getattr(request.app.state, "engine", None)
    if eng is None:
        raise HTTPException(status_code=503, detail="Engine unavailable")
    try:
        # Engine should implement enqueue_train(job, notes) and return a ticket id
        ticket = eng.enqueue_train(job=req.job, notes=req.notes)
        return {"ok": True, "ticket": ticket}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

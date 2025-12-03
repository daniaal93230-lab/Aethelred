"""
Batch 6C — Training Router (Aethelred v2)
-----------------------------------------
This file replaces all legacy train logic.

Training is fully asynchronous and routed through:
    services.engine_orchestrator.enqueue_train()

Endpoints:
  POST /train/job
  GET  /train/status/{ticket}
  GET  /train/jobs

All training is delegated to the orchestrator job queue.
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any, List


router = APIRouter(tags=["train"])


# ------------------------------------------------------------
# Pydantic Models (CI-safe, mypy-safe)
# ------------------------------------------------------------


class TrainJobRequest(BaseModel):
    job: str
    notes: Optional[str] = None


class TrainTicketResponse(BaseModel):
    ticket: str
    queued: bool


class TrainStatusResponse(BaseModel):
    ticket: str
    status: str
    attempts: int
    last_error: Optional[str] = None
    last_ts: Optional[float] = None


# ------------------------------------------------------------
# Helpers (extract orchestrator from DI)
# ------------------------------------------------------------


def _get_orchestrator(request: Request) -> Any:
    # Return type is Any because orchestrator is injected dynamically
    # and not statically typed.
    from typing import Any

    services: Any = getattr(request.app.state, "services", None)
    if services is None:
        raise HTTPException(status_code=503, detail="DI services unavailable")

    orch: Any = getattr(services, "engine_orchestrator", None)
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator unavailable")

    return orch


# ------------------------------------------------------------
# POST /train/job — submit training job
# ------------------------------------------------------------


@router.post("/train/job", response_model=TrainTicketResponse)
async def train_job(req: TrainJobRequest, request: Request) -> TrainTicketResponse:
    orch = _get_orchestrator(request)

    try:
        ticket = await orch.enqueue_train(job=req.job, notes=req.notes)
        return TrainTicketResponse(ticket=ticket, queued=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------
# GET /train/status/{ticket}
# ------------------------------------------------------------
@router.get("/train/status/{ticket}", response_model=TrainStatusResponse)
async def train_status(ticket: str, request: Request) -> TrainStatusResponse:
    orch = _get_orchestrator(request)

    # check inflight
    if ticket in getattr(orch, "_inflight", {}):
        meta = orch._inflight[ticket]
        t = meta["task"]
        return TrainStatusResponse(
            ticket=ticket,
            status="inflight",
            attempts=getattr(t, "attempts", 0),
            last_error=None,
            last_ts=meta.get("ts"),
        )

    # queued tasks
    # TaskQueue may not expose internals; best-effort snapshot:
    try:
        local_q = list(getattr(orch.queue, "_queue", []))  # noqa
    except Exception:
        local_q = []

    for task in local_q:
        if getattr(task, "ticket", None) == ticket:
            return TrainStatusResponse(
                ticket=ticket,
                status="queued",
                attempts=getattr(task, "attempts", 0),
                last_error=None,
                last_ts=getattr(task, "enqueued_ts", None),
            )

    # if seen in state, it succeeded or failed
    last_err = None
    last_ts = None
    try:
        last_err = orch.state.last_exception()
    except Exception:
        pass
    try:
        last_ts = orch.state.last_ts()
    except Exception:
        pass

    return TrainStatusResponse(
        ticket=ticket,
        status="unknown_or_complete",
        attempts=0,
        last_error=last_err,
        last_ts=last_ts,
    )


# ------------------------------------------------------------
# GET /train/jobs — recent tickets (best effort)
# ------------------------------------------------------------


@router.get("/train/jobs")
async def train_jobs(request: Request) -> Dict[str, Any]:
    orch = _get_orchestrator(request)

    jobs: List[Dict[str, Any]] = []

    # queued tasks
    try:
        local_q = list(getattr(orch.queue, "_queue", []))  # noqa
    except Exception:
        local_q = []

    for t in local_q:
        jobs.append(
            {
                "ticket": getattr(t, "ticket", None),
                "status": "queued",
                "attempts": getattr(t, "attempts", 0),
                "ts": getattr(t, "enqueued_ts", None),
            }
        )

    # inflight tasks
    for tid, meta in getattr(orch, "_inflight", {}).items():
        t = meta["task"]
        jobs.append(
            {
                "ticket": tid,
                "status": "inflight",
                "attempts": getattr(t, "attempts", 0),
                "ts": meta.get("ts"),
            }
        )

    return {"jobs": jobs}

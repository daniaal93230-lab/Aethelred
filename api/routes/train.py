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
        # If no engine is present (e.g., lightweight test/dev env), allow a
        # direct training fallback when the caller provides training payload
        # fields. This keeps the endpoint useful for quick dev runs.
        try:
            body = await request.json()
        except Exception:
            body = {}
        if "signals_csv" in body:
            try:
                from pathlib import Path
                from ml.train_intent_veto import train_intent_veto as _train

                signals_csv = Path(body.get("signals_csv"))
                candles_csv = Path(body.get("candles_csv", f"data/candles/{body.get('symbol','BTCUSDT')}.csv"))
                horizon = int(body.get("horizon", 12))
                symbol = str(body.get("symbol", "BTCUSDT"))
                outdir = Path(body.get("outdir", "models/intent_veto"))
                res = _train(signals_csv, candles_csv, outdir, horizon=horizon, symbol=symbol)
                return {"status": "ok", **res}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        raise HTTPException(status_code=503, detail="Engine unavailable")
    try:
        # Engine should implement enqueue_train(job, notes) and return a ticket id
        ticket = eng.enqueue_train(job=req.job, notes=req.notes)
        return {"ok": True, "ticket": ticket}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

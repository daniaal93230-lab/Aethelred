from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from risk.engine import RiskEngine

router = APIRouter(prefix="/qa/risk", tags=["qa"])
_eng = RiskEngine()


class PreTradeReq(BaseModel):
    symbol: str
    notional_usd: float
    est_loss_pct_equity: float
    leverage_after: float


@router.post("/pre_trade_check")
def pre_trade_check(req: PreTradeReq):
    """
    QA-only: call RiskEngine.pre_trade_checks and return the decision.
    """
    d = _eng.pre_trade_checks(
        symbol=req.symbol,
        notional_usd=req.notional_usd,
        est_loss_pct_equity=req.est_loss_pct_equity,
        leverage_after=req.leverage_after,
    )
    return {"allow": d.allow, "reason": d.reason, "details": d.details}


class PostTradeReq(BaseModel):
    pnl_day_pct: float
    note: Optional[str] = None


@router.post("/post_trade_update")
def post_trade_update(req: PostTradeReq):
    """
    QA-only: simulate end of trade day incremental update to breakers.
    """
    _eng.post_trade_update(pnl_day_pct=req.pnl_day_pct)
    return {"status": _eng.status()}

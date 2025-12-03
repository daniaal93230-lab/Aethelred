from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.risk import RiskEngine

router = APIRouter(prefix="/qa/risk", tags=["qa"])


class PreTradeReq(BaseModel):
    symbol: str
    notional_usd: float
    est_loss_pct_equity: float
    leverage_after: float


@router.post("/pre_trade_check")
def pre_trade_check(req: PreTradeReq, request: Request) -> Dict[str, Any]:
    """
    QA-only: call RiskEngine.pre_trade_checks and return the decision.
    """
    services = getattr(request.app.state, "services", None)
    risk = getattr(services, "risk", None) if services else None

    if risk is None:
        try:
            from core.risk import RiskEngine

            risk_engine: "RiskEngine" = RiskEngine({})
            risk = risk_engine
        except Exception:
            return {
                "allow": True,
                "reason": "no-risk-engine",
                "details": {},
            }

    d = risk.pre_trade_checks(
        symbol=req.symbol,
        notional_usd=req.notional_usd,
        est_loss_pct_equity=req.est_loss_pct_equity,
        leverage_after=req.leverage_after,
    )
    return {
        "allow": getattr(d, "allow", True),
        "reason": getattr(d, "reason", "unknown"),
        "details": getattr(d, "details", {}),
    }


class PostTradeReq(BaseModel):
    pnl_day_pct: float
    note: Optional[str] = None


@router.post("/post_trade_update")
def post_trade_update(req: PostTradeReq, request: Request) -> Dict[str, Any]:
    """
    QA-only: simulate end of trade day incremental update to breakers.
    """
    services = getattr(request.app.state, "services", None)
    risk = getattr(services, "risk", None) if services else None

    if risk is None:
        try:
            from core.risk import RiskEngine

            risk_engine: "RiskEngine" = RiskEngine({})
            risk = risk_engine
        except Exception:
            return {"status": "noop"}

    if risk is None or not hasattr(risk, "post_trade_update"):
        return {"status": "noop"}

    risk.post_trade_update(pnl_day_pct=req.pnl_day_pct)

    status = {}
    if hasattr(risk, "status"):
        try:
            status = risk.status()
        except Exception:
            status = {}

    return {"status": status}

import time
from fastapi import APIRouter
from typing import List, Dict, Any
from risk.engine import RiskEngine
from risk.taxonomy import Reason
from exchange.paper import PaperExchange
from utils.mtm import load_runtime_equity, compute_exposure_snapshot
from utils.aud import append_audit

router = APIRouter(prefix="/demo", tags=["demo"])

SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
NOTIONALS = [200, 150, 100]  # tiny notional for safety


@router.post("/paper_quick_run")
def paper_quick_run() -> Dict[str, Any]:
    """
    Quick smoke test: opens tiny positions if allowed by RiskEngine, then closes them.
    Returns a compact summary for QA.
    """
    risk = RiskEngine()
    ex = PaperExchange()

    equity_before = load_runtime_equity(risk.cfg)
    exposure_before = compute_exposure_snapshot(risk.cfg)

    opened: List[Dict[str, Any]] = []
    vetoes: List[Dict[str, Any]] = []

    # 1) Try to open tiny longs (paper)
    for sym, notional in zip(SYMS, NOTIONALS):
        pre = risk.pre_trade_checks(
            symbol=sym,
            notional_usd=float(notional),
            est_loss_pct_equity=0.5,
            leverage_after=1.0,
        )
        if not pre.allow:
            vetoes.append({"symbol": sym, "reason": pre.reason, "details": pre.details})
            continue
        try:
            fill = ex.market_buy_notional(sym, float(notional))
            opened.append(
                {
                    "symbol": sym,
                    "qty": float(fill.get("qty", 0) or 0),
                    "price": float(fill.get("price", 0) or 0),
                    "order_id": str(fill.get("order_id", "")),
                }
            )
        except Exception as e:
            vetoes.append({"symbol": sym, "reason": Reason.API_ERROR, "details": {"error": str(e)}})

    time.sleep(0.2)  # allow MTM sweep/heartbeat

    # 2) Close everything we just opened
    flattened = 0
    for o in opened:
        try:
            ex.market_close(o["symbol"])
            flattened += 1
        except Exception as e:
            append_audit(Reason.API_ERROR, {"op": "market_close", "symbol": o["symbol"], "err": str(e)})

    equity_after = load_runtime_equity(risk.cfg)
    exposure_after = compute_exposure_snapshot(risk.cfg)

    summary: Dict[str, Any] = {
        "opened": opened,
        "vetoes": vetoes,
        "flattened_count": flattened,
        "equity_before": float(equity_before),
        "equity_after": float(equity_after),
        "exposure_before": exposure_before,
        "exposure_after": exposure_after,
        "risk_status": risk.status(),
    }
    append_audit("DEMO_PAPER_RUN", summary)
    return summary

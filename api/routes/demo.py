from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from fastapi import Request  # ensure request type is imported

from api.deps.engine import get_engine  # injected engine instance
from api.deps.exchange import get_paper_exchange
from api.deps.risk import get_risk_engine


router = APIRouter(prefix="/demo", tags=["demo"])


# ----------------------------------------------------------------------
# Schemas
# ----------------------------------------------------------------------


class DemoPayload(BaseModel):
    symbol: str = Field("BTC/USDT", description="Trading symbol")
    side: str = Field("long", description="Direction: long/short")
    qty: float = Field(0.001, gt=0)
    price: Optional[float] = Field(None, description="Override market price")


class DemoResult(BaseModel):
    ok: bool
    symbol: str
    qty: float
    price: float
    side: str
    executed: bool
    meta: Dict[str, Any]


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _get_price(exchange: Any, symbol: str, override: Optional[float]) -> float:
    """
    Gets the current close price from the paper exchange,
    unless overridden by the request.
    """
    if override is not None:
        return override

    ohlcv = exchange.fetch_ohlcv(symbol)
    if not ohlcv or not isinstance(ohlcv[-1], list) or len(ohlcv[-1]) < 5:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No price available for {symbol}",
        )
    return float(ohlcv[-1][4])


# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------


@router.post("/market", response_model=DemoResult)
async def demo_market_order(
    payload: DemoPayload,
    engine: Any = Depends(get_engine),
    exchange: Any = Depends(get_paper_exchange),
    risk: Any = Depends(get_risk_engine),
) -> DemoResult:
    """
    Simulate a simple market order using the paper exchange.

    Does NOT affect production trading; safe for testing/demos.
    """

    price = _get_price(exchange, payload.symbol, payload.price)

    # Risk sanity
    if payload.qty <= 0:
        raise HTTPException(
            status_code=400,
            detail="Quantity must be positive.",
        )

    # Paper execution
    try:
        result = exchange.place_order(
            symbol=payload.symbol,
            side=payload.side,
            qty=payload.qty,
            price=price,
            order_type="market",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Execution error: {exc}",
        )

    return DemoResult(
        ok=True,
        symbol=payload.symbol,
        qty=payload.qty,
        price=price,
        side=payload.side,
        executed=True,
        meta={"exchange_result": result},
    )


@router.get("/ping")
async def demo_ping() -> Dict[str, Any]:
    """Simple health check for demo subsystem."""
    return {"ok": True, "msg": "demo online"}


@router.get("/signal")
async def demo_signal(request: Request, symbol: str = "BTC/USDT") -> Dict[str, Any]:
    """
    Return a demo signal. `test=1` query param returns legacy SMA raw string.
    Otherwise returns typed signal from the engine/router when available.
    """
    testing = request.query_params.get("test") == "1"

    engine = None
    try:
        engine = await Depends(get_engine)(request)
    except Exception:
        try:
            engine = get_engine(request)
        except Exception:
            engine = None

    exch = getattr(engine, "exchange", None) if engine is not None else None
    if exch is None:
        raise HTTPException(status_code=503, detail="Exchange unavailable")

    try:
        ohlcv = exch.fetch_ohlcv(symbol)
    except Exception:
        ohlcv = []

    if testing:
        from core.trade_logic import simple_moving_average_strategy

        raw = simple_moving_average_strategy(ohlcv)
        return {"signal": raw}

    strategos = getattr(engine, "_strategos", None) if engine is not None else None
    if strategos is None:
        from core.trade_logic import simple_moving_average_strategy

        raw = simple_moving_average_strategy(ohlcv)
        return {"signal": raw}

    typed = strategos.route(ohlcv)
    return {"signal": typed.side.value.lower(), "strength": typed.strength}

from __future__ import annotations

import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.services.risk_dashboard_builder import RiskDashboardBuilder


router = APIRouter(prefix="/ws", tags=["risk-dashboard-ws"])


# ---------------------------------------------------------
# WebSocket: /ws/risk/{symbol}
# Streams live RiskDashboard snapshots every 500ms
# ---------------------------------------------------------
@router.websocket("/risk/{symbol}")
async def ws_risk_dashboard(websocket: WebSocket, symbol: str):
    """
    Real-time risk stream:

    - Streams RiskDashboard snapshots
    - 500ms refresh interval by default
    - No caching (risk data must be hot)
    - Uses orchestrator, risk engine, and execution engine state

    Fully read-only and safe.
    """
    await websocket.accept()

    try:
        while True:
            app = websocket.app
            services = getattr(app.state, "services", None)

            if services is None:
                await websocket.send_json({"error": "services not initialized"})
                await asyncio.sleep(1)
                continue

            risk_engines = getattr(services, "risk_engines", None)
            orchestrator = getattr(services, "multi_orch", None)
            engines = getattr(services, "engines", None)

            if risk_engines is None or orchestrator is None or engines is None:
                await websocket.send_json({"error": "risk services unavailable"})
                await asyncio.sleep(1)
                continue

            if symbol not in risk_engines or symbol not in engines:
                await websocket.send_json({"error": f"symbol {symbol} not registered"})
                await asyncio.sleep(1)
                continue

            risk_engine = risk_engines[symbol]
            engine = engines[symbol]

            # Build real-time snapshot
            builder = RiskDashboardBuilder(
                symbol=symbol,
                risk_engine=risk_engine,
                orchestrator=orchestrator,
                engine=engine,
            )
            snapshot = builder.build()

            # Emit
            await websocket.send_json(snapshot.model_dump())

            # Default refresh: 500ms
            await asyncio.sleep(0.5)

    except WebSocketDisconnect:
        # Client disconnected normally
        return
    except Exception as e:
        try:
            await websocket.send_json({"error": str(e)})
        except Exception:
            pass
        return

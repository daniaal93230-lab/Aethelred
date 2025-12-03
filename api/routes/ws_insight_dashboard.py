from __future__ import annotations

import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.services.insight_dashboard_builder import InsightDashboardBuilder


router = APIRouter(prefix="/ws", tags=["insight-dashboard-ws"])


# ---------------------------------------------------------
# WebSocket: /ws/insight/{symbol}
# Streams InsightDashboard snapshots every N ms
# ---------------------------------------------------------
@router.websocket("/insight/{symbol}")
async def ws_insight_dashboard(websocket: WebSocket, symbol: str):
    """
    WS streaming endpoint:
      - Accepts WS clients
      - Emits InsightDashboard snapshots periodically
      - Uses TTL cache to reduce CPU load
      - Fully read-only
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

            insight_engines = getattr(services, "insight_engines", None)
            orchestrator = getattr(services, "multi_orch", None)
            history = getattr(services, "telemetry_history", None)

            if insight_engines is None or orchestrator is None or history is None:
                await websocket.send_json({"error": "telemetry unavailable"})
                await asyncio.sleep(1)
                continue

            if symbol not in insight_engines:
                await websocket.send_json({"error": f"no insight engine for symbol {symbol}"})
                await asyncio.sleep(1)
                continue

            # Build dashboard snapshot using TTL caching
            builder = InsightDashboardBuilder(
                insight_engine=insight_engines[symbol],
                orchestrator=orchestrator,
                history=history,
                symbol=symbol,
            )

            snapshot = builder.build()
            await websocket.send_json(snapshot.model_dump())

            # Stream interval — 500ms by default
            await asyncio.sleep(0.5)

    except WebSocketDisconnect:
        # client disconnected normally
        return
    except Exception as e:
        try:
            await websocket.send_json({"error": str(e)})
        except Exception:
            pass
        return

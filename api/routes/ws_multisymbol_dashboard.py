from __future__ import annotations

import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.services.multisymbol_dashboard_builder import MultiSymbolDashboardBuilder


router = APIRouter(prefix="/ws", tags=["multi-symbol-dashboard-ws"])


# ---------------------------------------------------------
# WebSocket: /ws/dashboard/multi
# Streams unified MultiSymbolDashboard snapshots
# ---------------------------------------------------------
@router.websocket("/dashboard/multi")
async def ws_multisymbol_dashboard(websocket: WebSocket):
    """
    Real-time streaming of the unified multi-symbol dashboard.

    This endpoint:
      - Aggregates risk + insight + ops for ALL symbols
      - Streams MultiSymbolDashboard snapshots every 1 second
      - Does not cache (data must remain hot and consistent)
      - Pure read-only; fully safe
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

            builder = MultiSymbolDashboardBuilder(services)

            try:
                snapshot = builder.build()
                await websocket.send_json(snapshot.model_dump())
            except Exception as e:
                await websocket.send_json({"error": str(e)})

            # Multi-symbol updates are heavier → 1 second interval
            await asyncio.sleep(1.0)

    except WebSocketDisconnect:
        return
    except Exception as e:
        try:
            await websocket.send_json({"error": str(e)})
        except Exception:
            pass
        return

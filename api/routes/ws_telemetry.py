from __future__ import annotations

import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from fastapi.encoders import jsonable_encoder

from api.deps.orchestrator_v2 import get_telemetry_bus


router = APIRouter(prefix="/ws", tags=["websocket"])


async def telemetry_stream(websocket: WebSocket, channel: str, telemetry_bus):
    """
    Subscribes to TelemetryBusV2 for a specific channel and forwards events
    to a WebSocket client.

    Each new event on the bus → pushed to websocket.
    """
    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue()

    # Bus callback → put into queue
    def on_msg(msg):
        try:
            queue.put_nowait(msg)
        except Exception:
            pass

    # Subscribe to channel
    telemetry_bus.subscribe(channel, on_msg)

    try:
        # Push any last known event immediately
        last = telemetry_bus.last(channel)
        if last is not None:
            await websocket.send_json(jsonable_encoder(last))

        while True:
            msg = await queue.get()
            await websocket.send_json(jsonable_encoder(msg))

    except WebSocketDisconnect:
        return
    except Exception:
        # Never break API server
        return


@router.websocket("/portfolio")
async def ws_portfolio(
    websocket: WebSocket,
    telemetry_bus=Depends(get_telemetry_bus),
):
    """Stream live portfolio telemetry."""
    await telemetry_stream(websocket, "portfolio", telemetry_bus)


@router.websocket("/symbol/{symbol}")
async def ws_symbol(
    websocket: WebSocket,
    symbol: str,
    telemetry_bus=Depends(get_telemetry_bus),
):
    """Stream live per-symbol telemetry."""
    channel = f"symbol.{symbol}"
    await telemetry_stream(websocket, channel, telemetry_bus)

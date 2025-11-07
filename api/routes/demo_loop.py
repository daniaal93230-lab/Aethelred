from __future__ import annotations

from fastapi import APIRouter
import asyncio
import httpx

router = APIRouter()


@router.post("/demo/paper_quick_loop")
async def demo_paper_quick_loop(secs: int = 60, sleep_ms: int = 750):
    """Continuously call /demo/paper_quick_run every ~sleep_ms for up to secs seconds.

    Returns:
        {ok: True, runs: count}
    """
    async with httpx.AsyncClient() as client:
        deadline = asyncio.get_event_loop().time() + float(secs)
        count = 0
        while asyncio.get_event_loop().time() < deadline:
            try:
                await client.post("http://127.0.0.1:8080/demo/paper_quick_run", json={})
                count += 1
            except Exception:
                break
            await asyncio.sleep(sleep_ms / 1000)
    return {"ok": True, "runs": count}

from __future__ import annotations

from typing import Any

from fastapi import Request

from api.deps.settings import Settings


async def create_db_pool(settings: Settings) -> Any:
    """
    Stub: your real DB pool/manager goes here.
    """
    return {"url": settings.DB_URL}


async def close_db_pool(pool: Any) -> None:
    pass


def get_db(request: Request):
    return request.app.state.db

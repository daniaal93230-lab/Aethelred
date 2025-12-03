from __future__ import annotations

from pydantic import BaseModel


class HealthStatus(BaseModel):
    status: str
    message: str


class ReadinessStatus(BaseModel):
    db_ready: bool
    engine_ready: bool
    message: str


class LiveStatus(BaseModel):
    engine_running: bool
    loops_active: bool
    message: str

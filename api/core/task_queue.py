"""
Async FIFO task queue for orchestrator.
Phase 1: in-memory asyncio.Queue
Upgradable to Redis / distributed queues without API changes.
"""

from __future__ import annotations
import asyncio
from typing import Any, Optional


class Task:
    """
    Generic task envelope.
    Types:
        - "train"
        - "cycle"
        - "shutdown"
        - "custom"
    """

    def __init__(self, kind: str, payload: Optional[dict] = None, *, ticket: Optional[str] = None, attempts: int = 0, enqueued_ts: Optional[float] = None):
        self.kind = kind
        self.payload = payload or {}
        # optional durable fields used by orchestrator
        self.ticket = ticket or f"{kind}-{int(enqueued_ts or 0)}"
        self.attempts = int(attempts or 0)
        self.enqueued_ts = float(enqueued_ts) if enqueued_ts is not None else None

    def __repr__(self) -> str:
        return f"Task(kind={self.kind}, ticket={self.ticket}, attempts={self.attempts}, payload={self.payload})"


class TaskQueue:
    """
    Simple async FIFO queue.
    """

    def __init__(self):
        self._queue: asyncio.Queue[Task] = asyncio.Queue()

    async def put(self, task: Task) -> None:
        await self._queue.put(task)

    def put_nowait(self, task: Task) -> None:
        self._queue.put_nowait(task)

    async def get(self) -> Task:
        return await self._queue.get()

    def empty(self) -> bool:
        return self._queue.empty()

    def size(self) -> int:
        return self._queue.qsize()

    def qsize(self) -> int:
        return self._queue.qsize()

    async def drain(self) -> list[Task]:
        """Return all tasks without blocking."""
        out = []
        while not self._queue.empty():
            out.append(self._queue.get_nowait())
        return out

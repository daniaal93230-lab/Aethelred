from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple


class TTLCache:
    """
    Lightweight per-symbol TTL cache for dashboard results.

    - No external deps
    - Safe for tests (not used outside the builder)
    - Cache invalidates automatically after TTL seconds
    - Stores arbitrary objects
    """

    def __init__(self, ttl_seconds: float = 2.0):
        self.ttl = ttl_seconds
        self._store: Dict[str, Tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None

        ts, value = entry
        if time.time() - ts > self.ttl:
            # expired
            self._store.pop(key, None)
            return None

        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.time(), value)

    def clear(self) -> None:
        self._store.clear()

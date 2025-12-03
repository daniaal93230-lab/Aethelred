"""
Persistent JSON state store for orchestrator.
Survives restarts, safe for async access.

Stores:
 - last_run_ts
 - last_regime
 - last_signal
 - last_exception
 - cadence_mode
"""

from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Any, Dict

STATE_PATH = Path("runtime/orchestrator_state.json")


class StateStore:
    def __init__(self, path: Path = STATE_PATH):
        self.path = path
        self._cached: Dict[str, Any] = {}
        self._loaded = False

    def _load(self) -> None:
        if not self._loaded:
            try:
                if self.path.exists():
                    self._cached = json.loads(self.path.read_text())
            except Exception:
                self._cached = {}
            self._loaded = True

    def _write(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._cached, indent=2))
        except Exception:
            pass

    # ---- Public API ----

    def get(self, key: str, default=None):
        self._load()
        return self._cached.get(key, default)

    def set(self, key: str, value: Any):
        self._load()
        self._cached[key] = value
        self._write()

    def update(self, data: Dict[str, Any]):
        self._load()
        self._cached.update(data)
        self._write()

    # Convenience fields

    def mark_run(self, regime: str, signal: str, symbol: str | None = None):
        data = {
            "last_run_ts": time.time(),
            "last_regime": regime,
            "last_signal": signal,
        }
        # per-symbol metadata
        if symbol:
            per = self.get("per_symbol", {})
            per[symbol] = {"last_run_ts": data["last_run_ts"], "last_regime": regime, "last_signal": signal}
            data["per_symbol"] = per

        self.update(data)

    def record_exception(self, err: str):
        self.set("last_exception", err)

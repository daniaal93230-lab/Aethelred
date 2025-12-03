from __future__ import annotations

from typing import Any, Callable, Dict, List


class TelemetryBusV2:
    """
    In memory telemetry bus for Aethelred.

    Simple pub/sub:
      - subscribe(channel, callback)
      - publish(channel, payload)

    Callbacks are called synchronously and must be fast.
    This is enough for Phase 4 telemetry and can be wrapped
    by API or websocket layers later.
    """

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Callable[[Any], None]]] = {}
        self._last_messages: Dict[str, Any] = {}

    def subscribe(self, channel: str, callback: Callable[[Any], None]) -> None:
        """
        Register a subscriber on a channel.
        """
        if channel not in self._subscribers:
            self._subscribers[channel] = []
        self._subscribers[channel].append(callback)

    def publish(self, channel: str, payload: Any) -> None:
        """
        Publish payload to a channel and notify subscribers.
        """
        self._last_messages[channel] = payload

        callbacks = self._subscribers.get(channel, [])
        for cb in callbacks:
            try:
                cb(payload)
            except Exception:
                # Telemetry errors must never affect trading loop
                continue

    def last(self, channel: str) -> Any:
        """
        Return last message for a channel, or None.
        """
        return self._last_messages.get(channel)

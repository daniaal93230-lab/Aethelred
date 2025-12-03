import asyncio
from typing import Optional, Dict, Any

import httpx
import threading


class OpsNotifier:
    """Central async notification dispatcher.

    Supports Telegram and Slack. Safe: never blocks orchestrators.
    """

    def __init__(
        self,
        telegram_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        slack_webhook: Optional[str] = None,
    ):
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
        self.slack_webhook = slack_webhook

    async def _send_telegram(self, text: str) -> None:
        if not self.telegram_token or not self.telegram_chat_id:
            return

        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload = {"chat_id": self.telegram_chat_id, "text": text}

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                await client.post(url, json=payload)
        except Exception:
            # swallow errors for safety
            pass

    async def _send_slack(self, text: str) -> None:
        if not self.slack_webhook:
            return

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                await client.post(self.slack_webhook, json={"text": text})
        except Exception:
            pass

    def send(self, category: str, cid: str | None = None, **details: Any) -> None:
        """Public interface. Dispatch async tasks without blocking caller.

        cid is an optional correlation id propagated from orchestrator per-cycle.
        """
        text = self._format(category, details, cid)
        # schedule fire-and-forget dispatch
        try:
            loop = asyncio.get_running_loop()
            # if we have a running loop, schedule a task
            loop.create_task(self._dispatch(text))
            return
        except Exception:
            # No running loop in caller. Dispatch on a background thread
            # using asyncio.run in that thread so caller never blocks.
            try:
                t = threading.Thread(target=lambda: asyncio.run(self._dispatch(text)), daemon=True)
                t.start()
            except Exception:
                pass

    async def _dispatch(self, text: str) -> None:
        await asyncio.gather(
            self._send_telegram(text),
            self._send_slack(text),
            return_exceptions=True,
        )

    def _format(self, category: str, details: Dict[str, Any], cid: str | None) -> str:
        parts = [f"[{category.upper()}]"]
        for k, v in details.items():
            parts.append(f"{k}: {v}")
        if cid:
            parts.append(f"cid={cid}")
        return " | ".join(parts)


# global default notifier instance; bootstrap can override attributes
notifier = OpsNotifier()


def get_notifier() -> OpsNotifier:
    return notifier

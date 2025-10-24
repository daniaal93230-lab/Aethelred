from dataclasses import dataclass
import os
import time
import threading
from typing import Callable, Dict, Any
from core.risk_config import get_risk_cfg as _legacy_get


def load_risk_cfg() -> Dict[str, Any]:
    return _legacy_get("config/risk.yaml")


_watcher_started = False
_watchers: list[Callable[[], None]] = []


def on_risk_cfg_change(cb: Callable[[], None], path: str = "config/risk.yaml", interval: float = 2.0) -> None:
    global _watcher_started
    if _watcher_started:
        _watchers.append(cb)
        return
    _watcher_started = True
    _watchers.append(cb)

    def _loop():
        last = 0.0
        while True:
            try:
                st = os.stat(path)
                if st.st_mtime > last:
                    last = st.st_mtime
                    cb()
            except FileNotFoundError:
                pass
            time.sleep(interval)

    th = threading.Thread(target=_loop, daemon=True)
    th.start()


def reload_risk_cfg() -> Dict[str, Any]:
    cfg = load_risk_cfg()
    for cb in list(_watchers):
        try:
            cb()
        except Exception:
            pass
    return cfg


# Backwards-compatible Settings dataclass used by the new unified runner.


@dataclass
class Settings:
    MODE: str = "paper"
    SAFE_START: bool = False
    PAPER_STARTING_CASH: float = 10000.0
    DAILY_LOSS_LIMIT_PCT: float = 0.05
    PER_TRADE_RISK_PCT: float = 0.01
    MAX_LEVERAGE: float = 1.5

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            MODE=os.getenv("MODE", "paper"),
            SAFE_START=os.getenv("SAFE_START", "0") in ("1", "true", "True"),
            PAPER_STARTING_CASH=float(os.getenv("PAPER_STARTING_CASH", "10000")),
            DAILY_LOSS_LIMIT_PCT=float(os.getenv("DAILY_LOSS_LIMIT_PCT", "0.05")),
            PER_TRADE_RISK_PCT=float(os.getenv("PER_TRADE_RISK_PCT", "0.01")),
            MAX_LEVERAGE=float(os.getenv("MAX_LEVERAGE", "1.5")),
        )

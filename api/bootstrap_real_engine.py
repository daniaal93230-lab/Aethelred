"""
Bootstrap the real engine and attach it to FastAPI for uvicorn --factory.
Usage:
    uvicorn api.bootstrap_real_engine:create_app --host 127.0.0.1 --port 8080
Env:
    LIVE=1                to prevent QA engine auto attach
    SAFE_FLATTEN_ON_START optional safety on startup
    SNAPSHOT_IDLE_SEC     optional idle snapshot loop interval (default 15)
"""

from __future__ import annotations
import os
import logging
from fastapi import FastAPI

# Import the FastAPI app and engine building blocks
from api.main import app as _app
from db.db_manager import DBManager
from risk.engine import RiskEngine
from core.risk_config import get_risk_cfg
from bot.exchange import Exchange

IDLE_SNAPSHOT_SEC = int(os.getenv("SNAPSHOT_IDLE_SEC", "15") or "15")

log = logging.getLogger("bootstrap")


class EngineOrchestrator:
    """
    Thin orchestrator surface that the API expects.
    Wraps exchange, risk, and db to expose:
      heartbeat, flatten_all, breakers_view, breakers_set,
      iter_trades, enqueue_train, account_snapshot, realized_pnl_today_usd, trade_count_today
    """

    def __init__(self, exch: Exchange, risk: RiskEngine, db: DBManager, clock=None):
        self._exch = exch
        self._risk = risk
        self._db = db
        self._clock = clock
        self._breakers = {"kill_switch": False, "manual_breaker": False, "daily_loss_tripped": False}
        self._last_tick_ts = None

    # -------- API surface --------
    def heartbeat(self) -> dict:
        # use exchange tick or db clock if available
        try:
            self._last_tick_ts = self._exch.last_tick_ts() or self._last_tick_ts
        except Exception:
            pass
        pos = self._exch.open_positions()
        return {"ok": True, "positions_count": len(pos), "last_tick_ts": self._last_tick_ts}

    async def flatten_all(self, reason: str = "") -> dict:
        return await self._exch.flatten_all(reason=reason)

    def breakers_view(self) -> dict:
        # merge risk breaker state if provided
        state = dict(self._breakers)
        try:
            r = self._risk.state_view()
            state.update({k: v for k, v in r.items() if k in ("kill_switch", "daily_loss_tripped")})
        except Exception:
            pass
        return state

    def breakers_set(self, kill_switch=None, manual_breaker=None, clear_daily_loss=None) -> dict:
        if kill_switch is not None:
            self._breakers["kill_switch"] = bool(kill_switch)
            try:
                self._risk.set_kill_switch(bool(kill_switch))
            except Exception:
                pass
        if manual_breaker is not None:
            self._breakers["manual_breaker"] = bool(manual_breaker)
        if clear_daily_loss:
            self._breakers["daily_loss_tripped"] = False
            try:
                self._risk.clear_daily_loss()
            except Exception:
                pass
        return self.breakers_view()

    def iter_trades(self):
        yield from self._db.iter_trades()

    def enqueue_train(self, job: str, notes: str | None = None):
        return self._db.enqueue_job(kind="train", job=job, notes=notes)

    def realized_pnl_today_usd(self) -> float:
        try:
            return float(self._db.realized_pnl_today_usd())
        except Exception:
            return 0.0

    def trade_count_today(self) -> int:
        try:
            return int(self._db.trade_count_today())
        except Exception:
            return 0

    def account_snapshot(self) -> dict:
        # delegate to exchange for positions and balances
        snap = self._exch.account_overview()
        snap["ts"] = self._clock_now()
        snap["realized_pnl_today_usd"] = self.realized_pnl_today_usd()
        snap["trade_count_today"] = self.trade_count_today()
        return snap

    # -------- helpers --------
    def _clock_now(self):
        try:
            return self._db.now_ts()
        except Exception:
            import time

            return int(time.time())


def create_app() -> FastAPI:
    os.environ["LIVE"] = os.getenv("LIVE", "1")
    db = DBManager()
    risk = RiskEngine(get_risk_cfg())
    exch = Exchange(db=db, risk=risk)
    engine = EngineOrchestrator(exch=exch, risk=risk, db=db)
    _app.state.engine = engine
    log.info("Real engine attached to app.state.engine")
    # start idle snapshot loop via api.main’s helper
    try:
        from api.main import start_idle_snapshot_loop

        start_idle_snapshot_loop(_app, interval_sec=IDLE_SNAPSHOT_SEC)
    except Exception as e:
        log.warning("Idle snapshot loop not started: %s", e)
    return _app

from __future__ import annotations
import asyncio, os, time
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

import ccxt.async_support as ccxt  # type: ignore
import pandas as pd
from fastapi import FastAPI

# ---------------- Config (env with defaults) ----------------
MODE = os.getenv("MODE", "PAPER")  # PAPER only in this module
EXCHANGE = os.getenv("EXCHANGE", "binance")
SYMBOLS = [s.strip() for s in os.getenv("SYMBOLS", "BTC/USDT").split(",") if s.strip()]
TIMEFRAME = os.getenv("TIMEFRAME", "1m")
POLL_SEC = int(os.getenv("POLL_SEC", "10"))
RISK_PCT = float(os.getenv("RISK_PCT", "0.02"))
LEVERAGE_MAX = float(os.getenv("LEVERAGE_MAX", "2"))
ALLOW_SHORTS = os.getenv("ALLOW_SHORTS", "false").lower() == "true"
START_ENGINE = os.getenv("START_ENGINE", "true").lower() == "true"
STARTING_CASH = float(os.getenv("PAPER_STARTING_CASH", "10000"))


# ---------------- Paper broker ----------------
@dataclass
class Position:
    symbol: str
    side: str  # "long" | "short"
    qty: float
    entry: float

    def unrealized(self, last: float) -> float:
        return (last - self.entry) * self.qty if self.side == "long" else (self.entry - last) * abs(self.qty)


@dataclass
class Trade:
    ts: float
    symbol: str
    side: str  # "buy" | "sell"
    qty: float
    price: float
    pnl: float = 0.0


class PaperBroker:
    def __init__(self, starting_cash: float, allow_shorts: bool = False, fee_bps: float = 5.0):
        self.cash = starting_cash
        self.allow_shorts = allow_shorts
        self.fee_bps = fee_bps
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []

    def equity(self, last_prices: Dict[str, float]) -> float:
        eq = self.cash
        for p in self.positions.values():
            last = last_prices.get(p.symbol)
            if last is not None:
                eq += p.unrealized(last)
        return eq

    def positions_snapshot(self) -> Dict[str, dict]:
        return {k: asdict(v) for k, v in self.positions.items()}

    def trades_snapshot(self) -> List[dict]:
        return [asdict(t) for t in self.trades[-200:]]

    def market_open(self, symbol: str, side: str, notional: float, last: float) -> Trade:
        if side == "short" and not self.allow_shorts:
            raise ValueError("Shorts disabled")
        if symbol in self.positions:
            raise ValueError("Position already open")
        qty = notional / last
        fee = last * qty * (self.fee_bps / 10_000)
        self.cash -= fee
        self.positions[symbol] = Position(symbol, side, qty if side == "long" else -qty, last)
        tr = Trade(time.time(), symbol, "buy" if side == "long" else "sell", qty, last, pnl=-fee)
        self.trades.append(tr)
        return tr

    def market_close(self, symbol: str, last: float) -> Optional[Trade]:
        pos = self.positions.pop(symbol, None)
        if not pos:
            return None
        side = "sell" if pos.side == "long" else "buy"
        pnl = pos.unrealized(last)
        fee = last * abs(pos.qty) * (self.fee_bps / 10_000)
        self.cash += pnl - fee
        tr = Trade(time.time(), symbol, side, abs(pos.qty), last, pnl=pnl - fee)
        self.trades.append(tr)
        return tr


# ---------------- Strategy: EMA crossover ----------------
class EmaCross:
    def __init__(self, fast: int = 12, slow: int = 26, allow_shorts: bool = False):
        self.fast, self.slow, self.allow_shorts = fast, slow, allow_shorts

    def signal(self, candles: pd.DataFrame) -> str:
        if len(candles) < max(self.fast, self.slow) + 2:
            return "flat"
        c = candles["close"]
        ema_f = c.ewm(span=self.fast, adjust=False).mean()
        ema_s = c.ewm(span=self.slow, adjust=False).mean()
        up = ema_f.iloc[-2] <= ema_s.iloc[-2] and ema_f.iloc[-1] > ema_s.iloc[-1]
        dn = ema_f.iloc[-2] >= ema_s.iloc[-2] and ema_f.iloc[-1] < ema_s.iloc[-1]
        if up:
            return "long"
        if self.allow_shorts and dn:
            return "short"
        return "flat"


def _candles_df(raw: List[List[float]]) -> pd.DataFrame:
    return pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])


# ---------------- Engine ----------------
class TradingEngine:
    def __init__(self) -> None:
        self.exchange = getattr(ccxt, EXCHANGE)({"enableRateLimit": True})
        self.strategy = EmaCross(allow_shorts=ALLOW_SHORTS)
        self.broker = PaperBroker(STARTING_CASH, allow_shorts=ALLOW_SHORTS)
        self._last_prices: Dict[str, float] = {}
        self._stop = asyncio.Event()

    async def run(self) -> None:
        try:
            while not self._stop.is_set():
                await self._tick()
                await asyncio.sleep(POLL_SEC)
        finally:
            await self.exchange.close()

    async def _tick(self) -> None:
        for symbol in SYMBOLS:
            try:
                ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=200)
                if not ohlcv:
                    continue
                df = _candles_df(ohlcv)
                last = float(df["close"].iloc[-1])
                self._last_prices[symbol] = last
                sig = self.strategy.signal(df)
                pos = self.broker.positions.get(symbol)
                if sig == "long":
                    if not pos:
                        self._open(symbol, "long", last)
                    elif pos.side == "short":
                        self.broker.market_close(symbol, last)
                        self._open(symbol, "long", last)
                elif sig == "short" and ALLOW_SHORTS:
                    if not pos:
                        self._open(symbol, "short", last)
                    elif pos.side == "long":
                        self.broker.market_close(symbol, last)
                        self._open(symbol, "short", last)
                else:
                    if pos:
                        self.broker.market_close(symbol, last)
            except Exception:
                continue

    def _open(self, symbol: str, side: str, last: float) -> None:
        equity = self.broker.equity(self._last_prices)
        notional = max(0.0, equity * RISK_PCT * LEVERAGE_MAX)
        if notional > 0:
            self.broker.market_open(symbol, side, notional, last)

    def status(self) -> Dict[str, Any]:
        eq = self.broker.equity(self._last_prices)
        return {
            "mode": MODE,
            "exchange": EXCHANGE,
            "symbols": SYMBOLS,
            "timeframe": TIMEFRAME,
            "poll_sec": POLL_SEC,
            "cash": round(self.broker.cash, 2),
            "equity": round(eq, 2),
            "risk_pct": RISK_PCT,
            "leverage_max": LEVERAGE_MAX,
            "allow_shorts": ALLOW_SHORTS,
        }


# ---------------- FastAPI ----------------
app = FastAPI(title="Aethelred Paper Bot")
_engine: TradingEngine | None = None


@app.on_event("startup")
async def _startup() -> None:
    global _engine
    if START_ENGINE:
        _engine = TradingEngine()
        asyncio.create_task(_engine.run())


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/status")
def status() -> Dict[str, Any]:
    if not _engine:
        return {"engine": "stopped"}
    return _engine.status()


@app.get("/positions")
def positions() -> Dict[str, Any]:
    if not _engine:
        return {}
    return _engine.broker.positions_snapshot()


@app.get("/trades")
def trades() -> Dict[str, Any]:
    if not _engine:
        return {"trades": []}
    return {"trades": _engine.broker.trades_snapshot()}

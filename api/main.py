# api/main.py
from __future__ import annotations

import io
import json
import math
import sqlite3, csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel

# Paths
ROOT = Path(__file__).resolve().parents[1]  # project root
DASH_DIR = ROOT / "dashboard"  # dashboard folder
METRICS_DIR = ROOT  # metrics live in project root
SETTINGS_PATH = Path("runtime_settings.json")
DEFAULT_SETTINGS = {"risk": 0.02, "max_pos": 1.0, "no_short": True, "circuit": False}
DB_PATH = Path("data/ledger.db")
DB_PATH.parent.mkdir(exist_ok=True)


def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS trades(
        pair TEXT, side TEXT, entry_ts TEXT, exit_ts TEXT,
        entry REAL, exit REAL, pnl REAL, pnl_pct REAL, hold_s INTEGER
    )""")
    # naive ingest (idempotent-ish): read *_ledger.csv, append rows not seen
    for led in Path(".").glob("*_ledger.csv"):
        with led.open("r", newline="", encoding="utf-8") as fh:
            rd = csv.DictReader(fh)
            rows = [
                (
                    r["symbol"],
                    r["signal"],
                    r["entry_time"],
                    r.get("exit_time", ""),
                    float(r.get("entry_price", 0) or 0),
                    float(r.get("exit_price", 0) or 0),
                    float(r.get("pnl", 0) or 0),
                    float(r.get("pnl_pct", 0) or 0),
                    int(r.get("hold_s", 0) or 0),
                )
                for r in rd
                if r.get("entry_time")
            ]
            cur.executemany("INSERT INTO trades VALUES(?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()


init_db()


def load_settings():
    try:
        return json.loads(SETTINGS_PATH.read_text("utf-8"))
    except Exception:
        return DEFAULT_SETTINGS.copy()


def save_settings(obj):
    SETTINGS_PATH.write_text(json.dumps(obj, indent=2), encoding="utf-8")


app = FastAPI(title="Aethelred API")  # <â€” named 'app' for uvicorn

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Helpers
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _isfinite(x) -> bool:
    try:
        return math.isfinite(float(x))
    except Exception:
        return False


def _sanitize(o):
    if isinstance(o, dict):
        return {k: _sanitize(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_sanitize(v) for v in o]
    if isinstance(o, float):
        return None if not _isfinite(o) else float(o)
    return o


def _tail_csv(path: Path, n: int) -> str:
    """Return last n rows (with header) of a CSV."""
    if not path.exists():
        return ""
    try:
        df = pd.read_csv(path)
        if n > 0 and len(df) > n:
            df = df.tail(n)
        with io.StringIO() as buf:
            df.to_csv(buf, index=False)
            return buf.getvalue()
    except Exception:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if not lines:
            return ""
        header, body = lines[0], lines[1:]
        body = body[-n:] if n > 0 else body
        return "\n".join([header] + body) + ("\n" if body else "")


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Static dashboard
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

if DASH_DIR.exists():
    app.mount("/assets", StaticFiles(directory=DASH_DIR), name="assets")


@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse('<meta http-equiv="refresh" content="0; url=/dashboard/"/>', status_code=200)


@app.get("/dashboard", response_class=HTMLResponse)
def dash_redirect():
    return HTMLResponse('<meta http-equiv="refresh" content="0; url=/dashboard/"/>', status_code=307)


@app.get("/dashboard/", response_class=HTMLResponse)
def dashboard():
    index_file = DASH_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h3>Dashboard not found</h3>", status_code=404)
    return FileResponse(str(index_file))


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Metrics
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@app.get("/metrics")
def list_metrics():
    files = [p.name for p in METRICS_DIR.glob("*_metrics.csv")]
    return {"metric_files": sorted(files)}


@app.get("/metrics/{name}", response_class=PlainTextResponse)
def get_metrics_csv(name: str, n: int = Query(200, ge=0, le=5000)):
    path = METRICS_DIR / name
    if not path.exists():
        return PlainTextResponse("", status_code=404)
    return PlainTextResponse(_tail_csv(path, n=n), status_code=200)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Signals (combine all *_signal.json)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@app.get("/signals")
def get_signals():
    data: Dict[str, dict] = {}
    for p in ROOT.glob("*_signal.json"):
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            data[p.name] = _sanitize(obj)
        except Exception:
            continue
    return JSONResponse(data)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Trades â€” closed last 24h + open positions
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _col(df: pd.DataFrame, *options: str) -> Optional[str]:
    """Find a column in df ignoring case."""
    lower = {c.lower(): c for c in df.columns}
    for o in options:
        if o in lower:
            return lower[o]
    return None


def _load_price_map_from_signals() -> Dict[str, float]:
    """Map symbol -> latest price from *_signal.json."""
    mp: Dict[str, float] = {}
    for p in ROOT.glob("*_signal.json"):
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            sym = str(obj.get("symbol") or "").strip()
            price = obj.get("price", None)
            if sym and isinstance(price, (int, float)) and _isfinite(price):
                mp[sym] = float(price)
        except Exception:
            continue
    return mp


def _detect_trades_and_open_positions(
    ledger_path: Path,
    price_map: Dict[str, float],
) -> Tuple[List[dict], List[dict]]:
    """
    From a ledger, reconstruct closed trades and open positions.
    Assumes rows include (case-insensitive) columns: ts, signal, price, symbol(optional).
    """
    if not ledger_path.exists():
        return [], []

    try:
        df = pd.read_csv(ledger_path)
    except Exception:
        return [], []

    c_ts = _col(df, "ts", "timestamp", "time")
    c_sig = _col(df, "signal")
    c_price = _col(df, "price", "close")
    c_sym = _col(df, "symbol", "pair")

    if not all([c_ts, c_sig, c_price]):
        return [], []

    df[c_ts] = pd.to_datetime(df[c_ts], utc=True, errors="coerce")
    df = df.dropna(subset=[c_ts])
    df = df.sort_values(c_ts)

    sig_map = {"LONG": 1, "SHORT": -1, "FLAT": 0}
    df["_side"] = df[c_sig].astype(str).map(sig_map).fillna(0).astype(int)
    df["_price"] = pd.to_numeric(df[c_price], errors="coerce").astype(float)
    if c_sym:
        df["_symbol"] = df[c_sym].astype(str)
    else:
        base = ledger_path.stem.split("_")[0].upper()
        # best effort: infer like BTC_ledger.csv -> BTC/USDT (if your ledgers always have /USDT you can adjust)
        df["_symbol"] = base

    closed: List[dict] = []
    pos = 0
    entry_row = None

    for _, row in df.iterrows():
        s = int(row["_side"])
        price = float(row["_price"])
        ts = row[c_ts].to_pydatetime()
        symbol = str(row["_symbol"])

        if pos == 0 and s != 0:
            pos = s
            entry_row = row
        elif pos != 0 and s != pos:
            # close previous
            entry_price = float(entry_row["_price"])
            exit_price = price
            side = "LONG" if pos > 0 else "SHORT"
            pnl_pct = (exit_price / entry_price - 1.0) * (1 if pos > 0 else -1)
            hold_mins = (ts - entry_row[c_ts].to_pydatetime()).total_seconds() / 60.0

            closed.append(
                {
                    "symbol": symbol,
                    "side": side,
                    "entry_time": entry_row[c_ts].to_pydatetime().isoformat(),
                    "exit_time": ts.isoformat(),
                    "entry_price": float(round(entry_price, 8)),
                    "exit_price": float(round(exit_price, 8)),
                    "pnl_pct": float(pnl_pct),
                    "holding_mins": float(round(hold_mins, 2)),
                }
            )

            # flip?
            pos = s
            entry_row = row if s != 0 else None

    # any open position?
    opens: List[dict] = []
    if pos != 0 and entry_row is not None:
        symbol = str(entry_row["_symbol"])
        entry_price = float(entry_row["_price"])
        side = "LONG" if pos > 0 else "SHORT"

        # current price: prefer signals, else last ledger price
        cur_price = price_map.get(symbol, float(df.iloc[-1]["_price"]))
        pnl_unreal = (cur_price / entry_price - 1.0) * (1 if pos > 0 else -1)
        hold_mins = (_now_utc() - entry_row[c_ts].to_pydatetime()).total_seconds() / 60.0

        opens.append(
            {
                "symbol": symbol,
                "side": side,
                "entry_time": entry_row[c_ts].to_pydatetime().isoformat(),
                "entry_price": float(round(entry_price, 8)),
                "current_price": float(round(cur_price, 8)),
                "unrealized_pct": float(pnl_unreal),
                "holding_mins": float(round(hold_mins, 2)),
            }
        )

    return closed, opens


def _gather_last24h(pattern: str, symbol: Optional[str]) -> dict:
    since = _now_utc() - timedelta(days=1)
    price_map = _load_price_map_from_signals()

    closed_all: List[dict] = []
    open_all: List[dict] = []

    for path in ROOT.glob(pattern):
        closed, opens = _detect_trades_and_open_positions(path, price_map)
        for t in closed:
            if datetime.fromisoformat(t["exit_time"].replace("Z", "+00:00")) >= since:
                if symbol is None or t["symbol"] == symbol:
                    closed_all.append(t)
        for p in opens:
            if symbol is None or p["symbol"] == symbol:
                open_all.append(p)

    closed_all.sort(key=lambda r: r["exit_time"], reverse=True)
    open_all.sort(key=lambda r: r["entry_time"], reverse=True)

    # closed summary
    total = len(closed_all)
    wins = sum(1 for r in closed_all if r.get("pnl_pct", 0.0) > 0)
    pnl_sum = sum(r.get("pnl_pct", 0.0) for r in closed_all)
    avg_pnl = (pnl_sum / total) if total else 0.0
    win_rate = (wins / total) if total else 0.0

    return _sanitize(
        {
            "as_of": _now_utc().isoformat(),
            "window": "24h",
            "closed_summary": {
                "count": total,
                "win_rate": win_rate,
                "pnl_sum": pnl_sum,
                "pnl_avg": avg_pnl,
            },
            "closed": closed_all,
            "open": open_all,
        }
    )


@app.get("/trades/last24h")
def trades_last24h(pattern: str = Query("*_ledger.csv"), symbol: Optional[str] = Query(None)):
    """Closed trades in last 24h + current open positions."""
    return JSONResponse(_gather_last24h(pattern=pattern, symbol=symbol))


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Health
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@app.get("/health")
def health():
    return {"ok": True, "time": _now_utc().isoformat()}


@app.get("/settings")
def get_settings():
    return load_settings()


class SettingsPayload(BaseModel):
    risk: float
    max_pos: float
    no_short: bool
    circuit: bool


@app.post("/settings")
def post_settings(payload: SettingsPayload):
    s = load_settings()
    s.update(payload.model_dump())
    save_settings(s)
    return {"ok": True, "settings": s}


@app.get("/trades/summary")
def trades_summary():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("""
      SELECT
        COUNT(*) as n,
        SUM(pnl) as pnl,
        AVG(pnl) as avg_pnl,
        SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END)*1.0/COUNT(*) as win_rate
      FROM trades
      WHERE datetime(entry_ts) >= datetime('now','-1 day')
    """)
    row = dict(cur.fetchone())
    con.close()
    return row

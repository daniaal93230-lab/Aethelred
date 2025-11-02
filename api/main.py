# api/main.py
from __future__ import annotations

import io
import json
import math
import sqlite3, csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import time
from typing import Any, List, Optional, Tuple

import pandas as pd
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from utils.logger import get_logger
from utils.config import Settings
from db.db_manager import ensure_compat_views
import base64
from fastapi.staticfiles import StaticFiles
from core.persistence import recent_stats_7d
from db.db_manager import (
    DB_PATH as PERSIST_DB_PATH,
    load_equity_series,
    init_db as persist_init_db,
    fetch_recent_decisions,
)
from core.runtime_state import RUNTIME_DIR
from core import news as newsmod
from core.risk_profile import pick_profile
from core.risk import RiskEngine
from core.risk_config import get_risk_cfg
from ops.notifier import send_telegram
from pydantic import BaseModel
from core.ml.stop_distance import StopDistanceRegressor
from core.ml.intent_veto import IntentVeto

# Paths
ROOT = Path(__file__).resolve().parents[1]  # project root
DASH_DIR = ROOT / "dashboard"  # dashboard folder
# Use active runtime directory imported from core.runtime_state
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
METRICS_DIR = RUNTIME_DIR
SETTINGS_PATH = Path("runtime_settings.json")
DEFAULT_SETTINGS = {"risk": 0.02, "max_pos": 1.0, "no_short": True, "circuit": False}
# Use persistence DB path (honors AET_DB_PATH)
DB_PATH = Path(PERSIST_DB_PATH)
DB_PATH.parent.mkdir(exist_ok=True)

KILL_FILE = RUNTIME_DIR / "killswitch.on"
# Initialize risk engine with current config (lazy re-read inside handler)
_RISK = RiskEngine(get_risk_cfg())

# Heartbeat storage for lightweight /healthz
LAST_HEARTBEAT: dict[str, Any] = {"ts": None}

#
# Simple self-contained dashboard HTML (no f-strings, no .format)
#
DASHBOARD_HTML = r"""
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Aethelred Dashboard</title>
    <style>
        :root {
            --bg: #0f172a;
            --panel: #111827;
            --text: #e5e7eb;
            --muted: #9ca3af;
            --green: #22c55e;
            --amber: #f59e0b;
            --red: #ef4444;
            --blue: #3b82f6;
        }
        html,body { margin:0; background:var(--bg); color:var(--text); font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial; }
        .wrap { max-width:1100px; margin:24px auto; padding:0 16px; }
        h1 { font-size:20px; margin:0 0 12px 0; font-weight:600; letter-spacing:.2px; }
        .grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap:12px; }
        .card { background:var(--panel); border:1px solid rgba(255,255,255,.06); border-radius:12px; padding:14px; }
        .row { display:flex; gap:8px; align-items:center; justify-content:space-between; }
        .k { color:var(--muted); font-size:12px; }
        .v { font-weight:600; font-size:13px; }
        .muted { color:var(--muted); font-size:12px; }
        .pill { display:inline-block; padding:2px 8px; border-radius:999px; font-size:12px; }
        .ok { background:rgba(34,197,94,.15); color:var(--green); }
        .warn { background:rgba(245,158,11,.15); color:var(--amber); }
        .bad { background:rgba(239,68,68,.15); color:var(--red); }
        .link { color:var(--blue); text-decoration:none; }
    .card-header { font-weight:700; margin-bottom:8px; font-size:13px; }
    .card-row { display:flex; align-items:center; justify-content:space-between; font-size:12px; padding:2px 0; }
        .intent-buy { color: var(--green); }
        .intent-sell { color: var(--red); }
        .intent-hold { color: var(--muted); }
        .top { display:flex; align-items:center; justify-content:space-between; margin-bottom:12px; }
        .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; }
                .footer { margin-top:16px; font-size:12px; color:var(--muted); display:flex; gap:14px; flex-wrap:wrap; }
                .err { background: rgba(239,68,68,.15); color: #fecaca; border:1px solid rgba(239,68,68,.35); padding:10px 12px; border-radius:10px; margin-bottom:12px; }
        .chip{padding:2px 8px;border-radius:9999px;background:#1f2a37;color:#d1d5db;font-size:12px}
        .chip.warn{background:#3b1d1d;color:#fca5a5}
        .chip.ok{background:#1d3b25;color:#86efac}
        .btn{padding:6px 10px;border:1px solid #334155;border-radius:8px;background:#0b1220;color:#e5e7eb}
        .row{display:flex; gap:12px}
    </style>
</head>
<body>
    <div class="wrap">
                <script>const DEFAULT_SIMPLE = false;</script>
                <div class="top">
                    <h1>Aethelred Dashboard</h1>
                    <div class="muted">
                        Polling <span class="mono">/metrics_json</span> every 5s ·
                        <span id="rtpath" class="mono"></span> ·
                        <button id="toggle" style="background:transparent;border:1px solid rgba(255,255,255,.15);color:#e5e7eb;border-radius:8px;padding:4px 8px;cursor:pointer;">
                            Pause
                        </button>
                    </div>
                                </div>
                <div id="simple" class="card" style="margin-bottom:16px">
                    <div class="row" style="justify-content:space-between; align-items:center">
                        <div>
                            <div style="font-size:22px; font-weight:700" id="eq_now">$0.00</div>
                            <div id="pnl_line" style="opacity:.8; margin-top:2px">PnL today: $0.00 (0.00%)</div>
                        </div>
                        <div style="display:flex; gap:8px">
                            <span class="chip" id="chip_trading">Trading</span>
                            <span class="chip" id="chip_breaker">Breaker</span>
                            <span class="chip" id="chip_kill">Kill OFF</span>
                            <span class="chip" id="chip_risk">conservative</span>
                        </div>
                        <button id="toggleBtn" class="btn">Advanced ▼</button>
                    </div>
                    <div id="simplePositions" style="margin-top:10px"></div>
                </div>

                <div id="advanced" style="display:none">
                <div id="err"></div>
                <div id="summary" class="grid"></div>
                        <div style="margin:10px 0 8px 0;">
                            <img id="eqchart" src="/equity_chart.png" alt="equity"
                                     onerror="this.style.display='none'"
                                     style="width:100%;max-width:660px;border-radius:10px;border:1px solid rgba(255,255,255,.06);" />
                        </div>
                <h1 style="margin-top:18px;">Symbols</h1>
                <div id="symbols" class="grid"></div>
                <h1 style="margin-top:18px;">Positions</h1>
                <div id="positions"></div>
                <div id="risk" style="margin-top:18px;"></div>
                <div class="footer">
            <a class="link" href="/metrics_json" target="_blank">Open /metrics_json</a>
            <a class="link" href="/runtime_files" target="_blank">List runtime files</a>
        </div>
                </div>
    </div>
    <script>
                // Initialize simple/advanced visibility
                document.addEventListener('DOMContentLoaded', ()=>{
                    try{
                        const adv = document.getElementById('advanced');
                        const btn = document.getElementById('toggleBtn');
                        const useSimple = (typeof DEFAULT_SIMPLE !== 'undefined') ? !!DEFAULT_SIMPLE : true;
                        adv.style.display = useSimple ? 'none' : 'block';
                        if (btn) btn.textContent = useSimple ? 'Advanced ▼' : 'Advanced ▲';
                    }catch(e){}
                });
                async function fetchJson(url){ const r = await fetch(url); return await r.json(); }
                function fmtUSD(x){ return '$' + (x||0).toFixed(2); }
                function pct(x){ return (x||0).toFixed(2) + '%'; }
                function renderSimplePositions(mx){
                    const pos = mx.positions || [];
                    if (!pos.length){
                        return '<div style="opacity:.8">No open positions</div>';
                    }
                    return pos.map(p=>{
                        const side = p.side || '—';
                        const s = p.symbol || '';
                        const e = p.entry_price || 0;
                        const pr = p.current_price || 0;
                        const ur = (p.unrealized_pct||0)*100;
                        const sign = ur>=0 ? '+' : '';
                        return `<div style="display:flex;gap:10px;justify-content:space-between;border-top:1px solid #1f2937;padding-top:6px;margin-top:6px">
                            <div><b>${s}</b> · ${side}</div>
                            <div>Entry ${e.toFixed(2)} → ${pr.toFixed(2)}</div>
                            <div style=\"min-width:80px;text-align:right\">${sign}${ur.toFixed(2)}%</div>
                        </div>`;
                    }).join('');
                }
                function setChip(id, text, state){
                    const el = document.getElementById(id);
                    el.textContent = text;
                    el.classList.remove('ok','warn');
                    if (state==='ok') el.classList.add('ok');
                    if (state==='warn') el.classList.add('warn');
                }
                async function tickSimple(){
                    try{
                        const [mx, rp, pnl] = await Promise.all([
                            fetchJson('/metrics_json'),
                            fetchJson('/risk_profile'),
                            fetchJson('/pnl_today')
                        ]);
                        document.getElementById('eq_now').textContent = fmtUSD(mx.equity);
                        const sign = pnl.pnl_today_abs >= 0 ? '+' : '';
                        document.getElementById('pnl_line').textContent =
                            `PnL today: ${sign}${fmtUSD(pnl.pnl_today_abs)} (${sign}${pct(pnl.pnl_today_pct)})`;
                        const breakerActive = mx.breaker && mx.breaker.active;
                        setChip('chip_trading', breakerActive ? 'Trading paused' : 'Trading', breakerActive ? 'warn' : 'ok');
                        setChip('chip_breaker', breakerActive ? 'Breaker active' : 'Breaker idle', breakerActive ? 'warn' : 'ok');
                        setChip('chip_risk', rp.profile || '—', '');
                        document.getElementById('simplePositions').innerHTML = renderSimplePositions(mx);
                    }catch(e){ /* ignore */ }
                }
                document.getElementById('toggleBtn').onclick = ()=>{
                    const adv = document.getElementById('advanced');
                    const btn = document.getElementById('toggleBtn');
                    const show = adv.style.display === 'none';
                    adv.style.display = show ? 'block' : 'none';
                    btn.textContent = show ? 'Advanced ▲' : 'Advanced ▼';
                };
        const fmt2 = (x) => Number.isFinite(x) ? x.toFixed(2) : "-";
        const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html!==undefined) e.innerHTML = html; return e; };
        async function fetchPath() { try { const r = await fetch("/runtime_path"); const j = await r.json(); document.getElementById("rtpath").textContent = j.runtime_dir || ""; } catch {} }
        function showErr(msg) {
            const box = document.getElementById("err");
            if (!msg) { box.innerHTML = ""; return; }
            box.innerHTML = "";
            box.append(el("div","err", msg));
        }
        async function fetchMetrics() { const r = await fetch("/metrics_json"); if (!r.ok) throw new Error("fetch failed: "+r.status); return await r.json(); }
            function renderSummary(root, m) {
            root.innerHTML = "";
            const card = el("div","card");
                const a = el("div","row"); a.append(el("div","k","Equity")); a.append(el("div","v","$"+fmt2(Number(m.equity ?? 0))));
                const b = el("div","row"); b.append(el("div","k","Cash")); b.append(el("div","v","$"+fmt2(Number(m.cash ?? 0))));
                const c = el("div","row"); c.append(el("div","k","Exposure")); c.append(el("div","v","$"+fmt2(Number(m.exposure_usd ?? 0))));
            const br = el("div","row");
            const pill = el("span","pill " + (m.breaker && m.breaker.active ? "bad" : "ok"), m.breaker && m.breaker.active ? "Breaker active" : "Breaker idle");
            br.append(el("div","k","Risk")); br.append(pill);
            card.append(a,b,c,br); root.append(card);
        }
    function renderSymbols(root, m) {
            root.innerHTML = "";
            const regimes = m.regimes || {};
            const intents = m.intents || {};
            const strategies = m.strategies || {};
            const planned = m.planned || {};
            const ml = m.ml || {};
            const newsMul = m.news_multiplier || 1.0;
            const positions = m.positions || [];
            const syms = new Set([...Object.keys(regimes), ...Object.keys(intents), ...Object.keys(strategies), ...Object.keys(planned), ...positions.map(p => p.symbol)]);
            if (!syms.size) {
                const empty = el("div","card");
                empty.append(el("div","muted","No runtime snapshots found in this directory."));
                root.append(empty);
                return;
            }
            syms.forEach(sym => {
                const card = el("div","card");
                const head = el("div","row");
                head.append(el("div","v mono", sym));
                const reg = regimes[sym]; const strat = strategies[sym]; const intent = intents[sym];
                const badge = el("span","pill "+(reg==="panic"?"bad":reg==="trend"?"ok":"warn"), reg ? reg : "unknown");
                head.append(badge);
                const srow = el("div","row"); srow.append(el("div","k","Strategy")); srow.append(el("div","v", strat || "n/a"));
                const irow = el("div","row");
                irow.append(el("div","k","Intent"));
                const intentTxt = (intent||"hold").toUpperCase();
                const cls = intentTxt==="BUY" ? "intent-buy" : intentTxt==="SELL" ? "intent-sell" : "intent-hold";
                const iv = el("div", "v " + cls, intentTxt);
                irow.append(iv);
                const mli = ml[sym] || {};
                const mlrow = el("div","row");
                mlrow.append(el("div","k","ML"));
                const mlv = (mli.vote||"neutral")+" · p="+(mli.p_up!=null ? Number(mli.p_up).toFixed(2) : "—");
                mlrow.append(el("div","v", mlv));
                const pos = positions.find(p => p.symbol===sym);
                const prow = el("div","row"); const price = pos && Number.isFinite(pos.current_price) ? pos.current_price : NaN;
                prow.append(el("div","k","Price")); prow.append(el("div","v", Number.isFinite(price)? fmt2(price) : "n/a"));
                const plan = planned[sym] || {};
                const pl = el("div","row"); pl.append(el("div","k","Planned"));
                const val = (plan.stop!=null || plan.tp!=null) ? "S "+fmt2(plan.stop)+" / TP "+fmt2(plan.tp) : "none";
                pl.append(el("div","v", val));
                const nrow = el("div","row"); nrow.append(el("div","k","News")); nrow.append(el("div","v","× "+Number(newsMul).toFixed(2)));
                card.append(head,srow,irow,mlrow,prow,pl,nrow); root.append(card);
            });
        }
        function renderPositions(root, m) {
            root.innerHTML = "";
            const pos = (m && m.positions) || [];
            const card = el("div","card");
            if (!pos.length) {
                card.append(el("div","muted","No open positions."));
                root.append(card);
                return;
            }
            const table = el("table", "mono");
            table.style.width = "100%";
            table.style.fontSize = "12px";
            table.style.borderSpacing = "0 6px";
            const header = [["Symbol","Side","Entry","Price","Unrl%","Held(min)"]];
            const makeRow = (cells, strong=false) => {
                const tr = document.createElement("tr");
                cells.forEach((c, i) => {
                    const td = document.createElement("td");
                    td.style.padding = "2px 8px";
                    td.style.whiteSpace = "nowrap";
                    td.innerText = c;
                    if (strong && i===0) { td.style.fontWeight = "700"; }
                    tr.append(td);
                });
                return tr;
            };
            header.forEach(h => table.append(makeRow(h, true)));
            pos.forEach(p => {
                table.append(makeRow([
                    p.symbol,
                    p.side || "-",
                    (Number.isFinite(p.entry_price) ? p.entry_price.toFixed(2) : "-"),
                    (Number.isFinite(p.current_price) ? p.current_price.toFixed(2) : "-"),
                    (Number.isFinite(p.unrealized_pct) ? (p.unrealized_pct*100).toFixed(2)+"%" : "-"),
                    (Number.isFinite(p.holding_mins) ? p.holding_mins.toFixed(0) : "-"),
                ]));
            });
            card.append(table);
            root.append(card);
        }
                let paused = false;
            async function tick() {
                    try {
                const m = await fetchMetrics();
                showErr("");
                if (!m || typeof m !== "object") throw new Error("bad payload");
                renderSummary(document.getElementById("summary"), m);
                renderSymbols(document.getElementById("symbols"), m);
                renderPositions(document.getElementById("positions"), m);
                // risk profile (poll every ~10s)
                try {
                    if (!tick._risk || Date.now() - tick._risk > 10000) {
                        const r = await fetch("/risk_profile");
                        if (r.ok) {
                            const rp = await r.json();
                            renderRisk(rp);
                            tick._risk = Date.now();
                        }
                    }
                } catch {}
                // cache-bust the equity chart every 15s (3 ticks)
                tick._n = (tick._n||0)+1;
                if (tick._n % 3 === 0) {
                    const img = document.getElementById("eqchart");
                    const u = new URL(img.src, window.location.href);
                    u.searchParams.set("t", Date.now().toString());
                    img.src = u.toString();
                }
            } catch (e) {
                showErr("Failed to fetch /metrics_json: " + (e && e.message ? e.message : e));
                console.error(e);
                        // Render safe defaults so the dashboard is never empty
                        renderSummary(document.getElementById("summary"), { equity: 0, cash: 0, exposure_usd: 0, breaker: { active: false } });
                        const empty = { regimes: {}, intents: {}, strategies: {}, planned: {}, positions: [] };
                        renderSymbols(document.getElementById("symbols"), empty);
                        renderPositions(document.getElementById("positions"), empty);
            }
        }
                // Render defaults immediately on load so layout isn't empty before first fetch
                renderSummary(document.getElementById("summary"), { equity: 0, cash: 0, exposure_usd: 0, breaker: { active: false } });
                renderSymbols(document.getElementById("symbols"), { regimes: {}, intents: {}, strategies: {}, planned: {}, positions: [] });
                renderPositions(document.getElementById("positions"), { positions: [] });
                fetchPath(); tick();
            setInterval(() => { if (!paused) tick(); }, 5000);
            document.getElementById("toggle").addEventListener("click", () => {
                paused = !paused;
                document.getElementById("toggle").textContent = paused ? "Resume" : "Pause";
            });
                        function renderRisk(rp){
                                const el = document.getElementById('risk');
                                if(!el) return;
                                const on = (x) => x ? 'on' : 'off';
                                const num = (x, d=2) => (typeof x === 'number' && isFinite(x)) ? x.toFixed(d) : '-';
                                el.innerHTML = `
                                    <div class="card">
                                        <div class="card-header">Risk</div>
                                        <div class="card-row"><span>Profile</span><span class="mono">${rp.profile || '-'}</span></div>
                                        <div class="card-row"><span>Risk x</span><span class="mono">${num(rp.risk_multiplier)}</span></div>
                                        <div class="card-row"><span>Leverage max</span><span class="mono">${num(rp.leverage_max)}x</span></div>
                                        <div class="card-row"><span>Per-trade risk</span><span class="mono">${num(rp.risk_per_trade_pct)}%</span></div>
                                        <div class="card-row"><span>Daily loss limit</span><span class="mono">${num(rp.max_daily_loss_pct)}%</span></div>
                                        <div class="card-row"><span>Auto-flatten on DLL</span><span class="mono">${on(rp.auto_flatten_on_dll)}</span></div>
                                    </div>
                                `;
                        }
    </script>
</body>
</html>
"""


def api_init_db():
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


api_init_db()


def load_settings():
    try:
        return json.loads(SETTINGS_PATH.read_text("utf-8"))
    except Exception:
        return DEFAULT_SETTINGS.copy()


def save_settings(obj):
    SETTINGS_PATH.write_text(json.dumps(obj, indent=2), encoding="utf-8")


app = FastAPI(title="Aethelred API")  # <â€” named 'app' for uvicorn
try:
    from api.routes import router as _routes_router

    app.include_router(_routes_router)
except Exception:
    # routes package optional; continue if not available
    pass

try:
    # Register train router (thin trigger endpoint)
    from api.routes import train as _train_routes

    app.include_router(_train_routes.router, tags=["train"])
except Exception:
    # It's fine if the train router isn't importable in some environments
    pass

try:
    # Register insight router which exposes consolidated performance metrics
    from api.routes import insight as _insight_routes

    app.include_router(_insight_routes.router)
except Exception:
    # Non-fatal if insight route can't be imported (e.g., lightweight test env)
    pass


# Auto-attach a lightweight QADevEngine when QA_DEV_ENGINE or QA_MODE env var is set.
@app.on_event("startup")
async def _maybe_attach_qa_engine():
    try:
        # Never attach QA engine in live contexts
        if os.getenv("LIVE", "0") == "1":
            try:
                log.info("LIVE=1 detected, skipping QADevEngine attach")
            except Exception:
                pass
            return None

        want = os.getenv("QA_DEV_ENGINE", "0") == "1" or os.getenv("QA_MODE", "0") == "1"
        if not want:
            return None

        # import local QA engine implementation; guard in case ops package not present
        try:
            from ops.qa_dev_engine import QADevEngine

            eng = QADevEngine()
            app.state.engine = eng
            try:
                log.warning("QADevEngine attached (QA_DEV_ENGINE or QA_MODE). Not for live trading.")
            except Exception:
                pass
            return eng
        except Exception as e:
            try:
                log.exception("Failed to attach QADevEngine: %s", e)
            except Exception:
                pass
            return None
    except Exception:
        # swallow errors to avoid blocking startup
        pass


# CORS (allow all for local UI clients)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Optional: set a default journal_db_path on app.state if not provided by the orchestrator
try:
    default_db = os.getenv("JOURNAL_DB_PATH", "").strip()
    if not default_db:
        candidate = os.path.join("data", "journal.db")
        if os.path.exists(candidate):
            default_db = candidate
    if default_db:
        setattr(app.state, "journal_db_path", default_db)
except Exception:
    pass

# Logger and settings
log = get_logger("api")
settings = Settings.load()

# Ensure compatibility views exist for exports
try:
    ensure_compat_views()
except Exception as e:
    log.exception("Failed to ensure DB compat views: %s", e)


@app.on_event("startup")
async def _safe_startup():
    """
    Safe start rule:
      1) If breaker is active, flatten immediately.
      2) If env SAFE_FLATTEN_ON_START=1 then flatten once on startup.
    """
    try:
        engine = getattr(app.state, "engine", None)
        if engine is None:
            log.warning("Engine missing on startup. Skipping safe start checks")
            return
        breakers = engine.breakers_view() if hasattr(engine, "breakers_view") else {}
        breaker_active = bool(
            breakers.get("kill_switch") or breakers.get("daily_loss_tripped") or breakers.get("manual_breaker")
        )
        env_request = os.getenv("SAFE_FLATTEN_ON_START", "0") == "1"
        if breaker_active or env_request:
            log.warning("Safe startup: breaker or env flag detected. Flattening all positions")
            await engine.flatten_all(reason="safe_startup")
    except Exception as e:
        log.exception("Safe startup sequence failed: %s", e)


# ML: stop distance regressor loader (lazy)
STOP_MODEL_PATH = ROOT / "models" / "stop_distance_regressor_v1.pkl"
_stop_model: Optional[StopDistanceRegressor] = None
_intent_model: Optional[IntentVeto] = None


def _get_stop_model() -> StopDistanceRegressor:
    global _stop_model
    if _stop_model is None:
        if not STOP_MODEL_PATH.exists():
            raise FileNotFoundError(f"Stop distance model not found: {STOP_MODEL_PATH}")
        _stop_model = StopDistanceRegressor(STOP_MODEL_PATH)
    return _stop_model


def _get_intent_model() -> IntentVeto:
    global _intent_model
    if _intent_model is None:
        path = ROOT / "models" / "intent_veto_v1.pkl"
        if not path.exists():
            raise FileNotFoundError(f"Intent veto model not found: {path}")
        _intent_model = IntentVeto(path)
    return _intent_model


# Export endpoints moved into `api.routes.export` for a defensive, version-tolerant implementation.
# See `api/routes/export.py` for /export/trades.csv and /export/decisions.csv implementations.


# Legacy in-process trainer was removed in favor of a dedicated train router in `api.routes.train`.


class StopInferPayload(BaseModel):
    symbol: str
    features: dict[str, float]


@app.post("/ml/stop_distance")
def ml_stop_distance(payload: StopInferPayload):
    """Infer a stop distance in ATR units for a given feature vector.

    Request: { symbol: string, features: { <feature>: number, ... } }
    Response: { symbol, stop_atr, horizon_bars, model_version, fit_stats }
    """
    try:
        # Support test stub via api_main._sd override if present
        globals().get("_sd") or _get_stop_model()
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


class VetoInferPayload(BaseModel):
    symbol: str
    features: dict[str, float]
    threshold: Optional[float] = None


@app.post("/ml/intent_veto")
def ml_intent_veto(payload: VetoInferPayload):
    try:
        model = globals().get("_iv") or _get_intent_model()
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    try:
        p_good = float(model.predict_proba(payload.features))
        thr = float(payload.threshold) if payload.threshold is not None else 0.55
        decision = "allow" if p_good >= thr else "veto"
        return JSONResponse(
            {
                "p_good": p_good,
                "threshold": thr,
                "decision": decision,
                "model_version": "intent_veto_v1",
                "fit_stats": getattr(model, "fit_stats", {}),
            }
        )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    try:
        stop_atr = float(model.predict_atr_units(payload.features))
        return JSONResponse(
            {
                "symbol": payload.symbol,
                "stop_atr": stop_atr,
                "horizon_bars": int(getattr(model, "horizon_bars", 20)),
                # Surface stem (no extension) for friendlier contract
                "model_version": (
                    STOP_MODEL_PATH.stem if isinstance(STOP_MODEL_PATH, Path) else "stop_distance_regressor_v1"
                ),
                "fit_stats": getattr(model, "fit_stats", {}),
            }
        )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


class FlattenReq(BaseModel):
    mode: Optional[str] = "paper"
    reason: Optional[str] = "manual"


@app.post("/flatten")
def flatten(req: FlattenReq | None = None):
    """Manually flatten all paper positions using latest mids.
    For tests or dry-run, echo mode and reason with an ok status.
    """
    try:
        # Echo-only response for compatibility with tests
        if req is not None:
            return JSONResponse({"status": "ok", "result": {"mode": req.mode, "reason": req.reason}})

        # Fallback to legacy behavior when no payload
        from core.execution_engine import ExecutionEngine
        from bot.exchange import PaperExchange

        eng = ExecutionEngine()
        symbols = list({"BTC/USDT", "ETH/USDT", "SOL/USDT"})
        try:
            mids = eng.fetch_latest_mid_prices(symbols)  # may not exist in all engines
        except Exception:
            mids = {}
        if isinstance(getattr(eng, "exchange", None), PaperExchange):
            exch = eng.exchange
            exch.market_close_all(mids)
            snap = exch.account_overview(mids)
        else:
            snap = {
                "equity": getattr(getattr(eng, "db", object()), "get_latest_equity", lambda: 0.0)() or 0.0,
                "positions": [],
            }
        return JSONResponse(
            {"status": "flattened", "equity": float(snap.get("equity", 0.0)), "positions": snap.get("positions", [])}
        )
    except Exception as e:
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)


@app.get("/healthz")
def healthz():
    now = datetime.now(timezone.utc).isoformat()
    snap = {
        "now_utc": now,
        "last_heartbeat": LAST_HEARTBEAT.get("ts"),
        "db_present": Path(DB_PATH).exists(),
    }
    return {"status": "ok", "snapshot": snap}


@app.post("/train")
def train_intent_veto_endpoint(payload: dict):
    """
    Kick off training and write artifacts under models/intent_veto.
    Body:
        {
            "signals_csv": "data/decisions.csv",
            "candles_csv": "data/candles/BTCUSDT.csv",
            "horizon": 12,
            "symbol": "BTCUSDT"
        }
    """
    try:
        from pathlib import Path
        from ml.train_intent_veto import train_intent_veto as _train

        signals_csv = Path(payload.get("signals_csv", "data/decisions.csv"))
        candles_csv = Path(payload.get("candles_csv", f"data/candles/{payload.get('symbol','BTCUSDT')}.csv"))
        horizon = int(payload.get("horizon", 12))
        symbol = str(payload.get("symbol", "BTCUSDT"))
        outdir = Path("models/intent_veto")
        res = _train(signals_csv, candles_csv, outdir, horizon=horizon, symbol=symbol)
        return {"status": "ok", **res}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"train failed: {e}")


@app.get("/db_path")
def db_path():
    return {"db_path": str(DB_PATH.resolve())}


@app.on_event("startup")
async def _startup_news_loop():
    """Background task to fetch RSS, score sentiment, and write a sizing multiplier."""
    try:
        RUNTIME_DIR.mkdir(exist_ok=True)
    except Exception:
        pass
    # Ensure persistence DB tables exist early and schema verified
    try:
        persist_init_db()
        from db.db_manager import verify_schema

        try:
            verify_schema()
        except Exception as se:
            # Surface schema errors prominently on startup
            print(f"[API] Schema verification failed: {se}")
    except Exception:
        pass
    import asyncio, json as _json

    async def _news_loop():
        feeds = (
            os.getenv("NEWS_FEEDS") or "https://feeds.feedburner.com/CoinDesk,https://cointelegraph.com/rss"
        ).split(",")
        outp = RUNTIME_DIR / "news_state.json"
        out_items = RUNTIME_DIR / "news_items.json"
        while True:
            try:
                items = newsmod.fetch_rss(feeds, max_items=40)
                scored = newsmod.score_sentiment(items)
                mul = newsmod.risk_modifier_from_news(scored, window=20)
                payload = {"multiplier": float(mul)}
                outp.write_text(_json.dumps(payload), encoding="utf-8")
                # keep a tiny rolling window for UI/debug
                out_items.write_text(_json.dumps(scored[-30:], ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
            await asyncio.sleep(600)  # 10 minutes

    asyncio.create_task(_news_loop())

    # Optional daily report pinger (calls our own endpoint)
    async def _daily_report_loop():
        import datetime, asyncio, httpx

        while True:
            try:
                now = datetime.datetime.utcnow()
                tomorrow = now + datetime.timedelta(days=1)
                target = datetime.datetime(tomorrow.year, tomorrow.month, tomorrow.day, 23, 59, 0)
                await asyncio.sleep(max(60.0, (target - now).total_seconds()))
                async with httpx.AsyncClient() as c:
                    await c.get("http://127.0.0.1:8080/report/daily", timeout=10)
            except Exception:
                await asyncio.sleep(3600)

    if os.getenv("ENABLE_DAILY_REPORT", "1").lower() not in ("0", "false", "no"):
        asyncio.create_task(_daily_report_loop())


@app.get("/report/daily")
def report_daily():
    """
    Returns a compact daily summary and pushes Telegram if env is set.
    """
    try:
        series = load_equity_series(limit=1440)  # ~1 day of minute snapshots if recorded each loop
        eq_now = float(series[-1][1]) if series else None
        eq_start = float(series[0][1]) if series else None
        pnl_abs = (eq_now - eq_start) if (eq_now is not None and eq_start is not None) else None
        pnl_pct = (pnl_abs / eq_start * 100.0) if (pnl_abs is not None and eq_start and eq_start > 0) else None
        stats = recent_stats_7d()
        payload = {
            "equity_start": eq_start,
            "equity_now": eq_now,
            "pnl_abs": pnl_abs,
            "pnl_pct": pnl_pct,
            "trades_7d": stats.get("trades_last_7d", 0),
            "winrate_7d": stats.get("winrate_7d", None),
            "expectancy_7d_usd": stats.get("expectancy_7d_usd", None),
        }
        # Telegram (optional)
        if os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
            try:
                if (
                    eq_now is not None
                    and eq_start is not None
                    and payload.get("winrate_7d") is not None
                    and payload.get("expectancy_7d_usd") is not None
                ):
                    msg = (
                        f"<b>Aethelred Daily</b>\n"
                        f"Equity: {eq_now:.2f} (start {eq_start:.2f})\n"
                        f"PnL: {float(pnl_abs):+.2f} ({float(pnl_pct):+.2f}%)\n"
                        f"7d trades: {payload['trades_7d']}, winrate: {(payload['winrate_7d'] * 100):.1f}% | exp: {payload['expectancy_7d_usd']:.2f}"
                    )
                else:
                    msg = "<b>Aethelred Daily</b>\nNo sufficient stats yet."
                send_telegram(msg)
            except Exception:
                pass
        return payload
    except Exception as e:
        return {"error": str(e)}


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


def _load_account_runtime() -> dict:
    """Load account-level runtime snapshot if present."""
    try:
        p = RUNTIME_DIR / "account_runtime.json"
        if p.exists():
            # accept utf-8 with BOM
            return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        pass
    return {}


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Static dashboard
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

if DASH_DIR.exists():
    app.mount("/assets", StaticFiles(directory=DASH_DIR), name="assets")


@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse('<meta http-equiv="refresh" content="0; url=/dashboard/"/>', status_code=200)


@app.get("/dashboard", response_class=HTMLResponse)
@app.get("/dashboard/", response_class=HTMLResponse)
def dashboard(mode: Optional[str] = Query(default=None, description="simple|advanced")):
    html = DASHBOARD_HTML
    # Allow overriding default simple/advanced via query or env
    default_simple_env = os.getenv("DASHBOARD_SIMPLE", "1").lower() in ("1", "true", "yes")
    if mode == "simple":
        html = html.replace("const DEFAULT_SIMPLE = false;", "const DEFAULT_SIMPLE = true;")
    elif mode == "advanced":
        html = html.replace("const DEFAULT_SIMPLE = false;", "const DEFAULT_SIMPLE = false;")
    else:
        html = html.replace(
            "const DEFAULT_SIMPLE = false;",
            f"const DEFAULT_SIMPLE = {'true' if default_simple_env else 'false'};",
        )
    return HTMLResponse(html, status_code=200)


@app.get("/runtime_path")
def runtime_path():
    return {"runtime_dir": str(RUNTIME_DIR)}


@app.get("/runtime_files")
def runtime_files():
    files = []
    if RUNTIME_DIR.exists():
        for p in sorted(RUNTIME_DIR.glob("*_runtime.json")):
            try:
                files.append({"name": p.name, "size": p.stat().st_size})
            except Exception:
                continue
    return {"runtime_dir": str(RUNTIME_DIR), "files": files}


@app.post("/kill_switch/on")
def kill_on():
    try:
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        KILL_FILE.write_text("1", encoding="utf-8")
        return {"kill": "on"}
    except Exception:
        return {"kill": "on", "ok": False}


@app.post("/kill_switch/off")
def kill_off():
    try:
        if KILL_FILE.exists():
            KILL_FILE.unlink()
        return {"kill": "off"}
    except Exception:
        return {"kill": "off", "ok": False}


@app.get("/equity_chart.png")
def equity_chart_png(limit: int = 2000):
    """
    Minimal PNG chart of equity from SQLite.
    Falls back to a 1x1 transparent PNG if matplotlib is unavailable.
    """
    try:
        import io
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        # 1x1 transparent PNG
        tiny = base64.b64decode(
            b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/ae0fGQAAAAASUVORK5CYII="
        )
        return Response(content=tiny, media_type="image/png")

    try:
        series = load_equity_series(limit=limit)
    except Exception:
        series = []
    fig, ax = plt.subplots(figsize=(6, 2.2), dpi=160)
    # transparent background so it blends with the dark page
    fig.patch.set_alpha(0.0)
    ax.set_facecolor((0, 0, 0, 0))
    ax.tick_params(colors="#9ca3af", labelsize=7)
    if series:
        xs = [i for i, _ in enumerate(series)]
        ys = [v for _, v in series]
        if len(xs) == 1:
            # pad to avoid "identical low/high xlims" and show a small line
            xs = [0, 1]
            ys = [ys[0], ys[0]]
        ax.plot(xs, ys)
        ax.set_xlim(0, max(1, len(xs) - 1))
        ax.set_title("Equity", fontsize=9, color="#d1d5db")
    else:
        ax.set_title("Equity (no data)", fontsize=9, color="#9ca3af")
    ax.grid(True, alpha=0.15)
    for spine in ("top", "right", "left", "bottom"):
        ax.spines[spine].set_visible(False)
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return Response(content=buf.getvalue(), media_type="image/png")


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
    data: dict[str, dict] = {}
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


def _load_price_map_from_signals() -> dict[str, float]:
    """Map symbol -> latest price from *_signal.json."""
    mp: dict[str, float] = {}
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
    price_map: dict[str, float],
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


@app.get("/news_state")
def news_state():
    try:
        p = RUNTIME_DIR / "news_state.json"
        if not p.exists():
            return {"multiplier": 1.0, "updated": None}
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        return {
            "multiplier": float(data.get("multiplier", 1.0)),
            "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(p.stat().st_mtime)),
        }
    except Exception:
        return {"multiplier": 1.0, "updated": None}


@app.get("/news")
def news_items(limit: int = 20):
    try:
        p = RUNTIME_DIR / "news_items.json"
        if not p.exists():
            return []
        items = json.loads(p.read_text(encoding="utf-8-sig"))
        return items[-int(limit) :]
    except Exception:
        return []


@app.get("/metrics_json")
def metrics_json(debug: int = 0):
    """
    Return a compact dashboard JSON:
      now, equity, cash, exposure_usd, breaker, regimes, intents, positions, trades_last_24h, winrate_7d, expectancy_7d_usd
    Data is stitched from existing CSVs if present. Falls back to zeros.
    """
    now = _now_utc()
    # try last24h summary
    summary = _gather_last24h(pattern="*_ledger.csv", symbol=None)

    # Prefer account-level runtime snapshot if available
    acct = _load_account_runtime()
    equity = float(acct.get("equity", 0.0) or 0.0)
    cash = float(acct.get("cash", 0.0) or 0.0)
    exposure = float(acct.get("exposure_usd", 0.0) or 0.0)
    positions_raw = acct.get("positions") or []
    # Normalize positions to richer fields consumed by dashboard
    positions = []
    for p in positions_raw:
        try:
            positions.append(
                {
                    "symbol": p.get("symbol"),
                    "side": p.get("side"),
                    "qty": float(p.get("qty", 0.0) or 0.0),
                    "entry_price": float(p.get("avg_price", p.get("entry", 0.0)) or 0.0),
                    "current_price": float(p.get("market_price", p.get("price", 0.0)) or 0.0),
                    "unrealized_pct": float(p.get("unrealized_pct", 0.0) or 0.0),
                    "holding_mins": float(p.get("holding_mins", 0.0) or 0.0),
                }
            )
        except Exception:
            continue
    if not positions:
        # fallback to open positions reconstructed from ledgers
        positions = summary.get("open", [])
        # exposure approximation from open positions
        exposure = 0.0
        for p in positions:
            try:
                qty = float(p.get("qty") or (p.get("amount") or 0.0))
                price = float(p.get("price") or p.get("current_price") or 0.0)
                exposure += abs(qty * price)
            except Exception:
                continue

    closed = summary.get("closed_summary", {})
    trades24 = int(closed.get("count", 0))
    winrate7 = float(closed.get("win_rate", 0.0) or 0.0)
    expectancy7 = float(closed.get("pnl_avg", 0.0) or 0.0)
    # prefer DB stats if available
    try:
        s = recent_stats_7d()
        if s.get("trades_last_7d", 0) > 0:
            winrate7 = float(s.get("winrate_7d", winrate7))
            expectancy7 = float(s.get("expectancy_7d_usd", expectancy7))
            trades24 = max(trades24, int(s.get("trades_last_7d", 0)))
    except Exception:
        pass

    # augment with runtime snapshots if available
    regimes: dict[str, str] = {}
    intents: dict[str, str] = {}
    strategies: dict[str, str] = {}
    planned: dict[str, dict] = {}
    ml: dict[str, dict[str, object]] = {}
    gate_reason: dict[str, str] = {}
    breaker = {"active": False, "cooldown_remaining_sec": 0}
    debug_files: List[str] = []
    debug_errors: List[str] = []
    debug_info = {"runtime_dir": str(RUNTIME_DIR), "files_seen": debug_files, "errors": debug_errors} if debug else None
    try:
        if RUNTIME_DIR.exists():
            for p in RUNTIME_DIR.glob("*_runtime.json"):
                try:
                    if debug_info is not None:
                        debug_files.append(p.name)
                    # PowerShell often writes UTF-8 with BOM; accept both.
                    with open(p, "r", encoding="utf-8-sig") as fh:
                        raw = fh.read()
                    obj = json.loads(raw)
                    sym = str(obj.get("symbol") or "")
                    if not sym:
                        continue
                    if "regime" in obj:
                        regimes[sym] = str(obj["regime"]) or "unknown"
                    if "intent" in obj:
                        intents[sym] = str(obj["intent"]) or "hold"
                    if "strategy" in obj:
                        strategies[sym] = str(obj["strategy"]) or "unknown"
                    stp = obj.get("planned_stop")
                    tp = obj.get("planned_tp")
                    if stp is not None or tp is not None:
                        planned[sym] = {"stop": stp, "tp": tp}
                    if ("ml_p_up" in obj) or ("ml_vote" in obj):
                        ml[sym] = {"p_up": obj.get("ml_p_up"), "vote": obj.get("ml_vote")}
                    if isinstance(obj.get("gate_reason"), str) and obj.get("gate_reason"):
                        gate_reason[sym] = str(obj.get("gate_reason"))
                    if "breaker" in obj and isinstance(obj["breaker"], dict):
                        # simple OR on active
                        if bool(obj["breaker"].get("active")):
                            breaker["active"] = True
                except Exception as e:
                    if debug_info is not None:
                        debug_errors.append(str(e))
                    continue
    except Exception:
        pass

    # read news multiplier if background loop produced it
    news_multiplier = 1.0
    try:
        p = RUNTIME_DIR / "news_state.json"
        if p.exists():
            news_multiplier = float(json.loads(p.read_text(encoding="utf-8-sig")).get("multiplier", 1.0))
    except Exception:
        pass

    # derive simple portfolio gauges for risk display
    equity_now = float(equity)
    total_notional = float(exposure)
    # Test/QA hook: if a module-level get_positions() is provided (e.g., monkeypatched in tests),
    # use it to compute a synthetic total_notional_usd without touching the DB.
    try:
        gp = globals().get("get_positions")
        if callable(gp):
            lst = gp()
            tot = 0.0
            for it in lst or []:
                try:
                    n = it.get("notional_usd")
                    if n is None:
                        qty = float(it.get("qty") or 0.0)
                        px = float(it.get("market_price", it.get("current_price", 0.0)) or 0.0)
                        n = abs(qty * px)
                    tot += float(n or 0.0)
                except Exception:
                    continue
            # only override if we actually computed something meaningful
            if tot > 0:
                total_notional = float(tot)
    except Exception:
        pass
    cfg = get_risk_cfg()
    exp_cfg = cfg.get("exposure", {})
    max_expo = (
        (float(exp_cfg.get("max_exposure_usd", 0.35)) * equity_now)
        if exp_cfg.get("set_as_fraction", True)
        else float(exp_cfg.get("max_exposure_usd", 0.0))
    )
    lev = (total_notional / equity_now) if equity_now > 0 else 0.0

    payload: dict[str, Any] = {
        "now": int(now.timestamp()),
        "equity": float(equity),
        "db_equity": None,
        "runtime_equity": float(equity),
        "cash": float(cash),
        "exposure_usd": float(exposure),
        "breaker": breaker,
        "regimes": dict(regimes),
        "intents": dict(intents),
        "positions": list(positions),
        "strategies": dict(strategies)
        if isinstance(strategies, dict)
        else {"items": list(strategies) if isinstance(strategies, (list, tuple)) else {}},
        "planned": dict(planned)
        if isinstance(planned, dict)
        else {"items": list(planned) if isinstance(planned, (list, tuple)) else {}},
        "ml": dict(ml) if isinstance(ml, dict) else {},
        "gate_reason": gate_reason,
        "news_multiplier": news_multiplier,
        "trades_last_24h": trades24,
        "winrate_7d": winrate7,
        "expectancy_7d_usd": expectancy7,
        "risk": {
            "kill_switch": bool(cfg.get("kill_switch", False)),
            "breaker_daily_limit_pct": float(cfg.get("daily_loss_limit_pct", 3.0)),
            "per_trade_risk_pct": float(cfg.get("per_trade_risk_pct", 0.5)),
            "max_leverage": float(cfg.get("max_leverage", 1.5)),
            "portfolio": {
                "equity_now": equity_now,
                "total_notional_usd": total_notional,
                "max_exposure_usd": max_expo,
                "leverage": lev,
            },
        },
    }
    if debug_info is not None:
        payload["debug"] = debug_info
    # Attach dual equity sources when available
    try:
        series = load_equity_series(limit=1)
        if series:
            payload["db_equity"] = float(series[-1][1])
    except Exception:
        pass
    # runtime_equity already set to equity above
    return JSONResponse(_sanitize(payload))


@app.get("/pnl_today")
def pnl_today():
    """
    Compute today's PnL using the equity series from persistence.
    Returns equity_now, equity_sod, pnl_today_abs, pnl_today_pct.
    """
    try:
        series = load_equity_series(limit=2880)
        # Convert ts which may be ISO string or epoch seconds into UTC timestamps
        xs: List[float] = []
        ys: List[float] = []
        for ts_val, eq in series:
            try:
                if isinstance(ts_val, (int, float)):
                    xs.append(float(ts_val))
                else:
                    dt = datetime.fromisoformat(str(ts_val).replace("Z", "+00:00"))
                    xs.append(dt.replace(tzinfo=timezone.utc).timestamp())
                ys.append(float(eq))
            except Exception:
                continue
        now_eq = ys[-1] if ys else 0.0
        today_utc = datetime.now(timezone.utc).date()
        sod = None
        for x, y in zip(xs, ys):
            if datetime.fromtimestamp(x, tz=timezone.utc).date() == today_utc:
                sod = y
                break
        if sod is None:
            sod = now_eq
        pnl_abs = now_eq - sod
        pnl_pct = (pnl_abs / sod * 100.0) if sod else 0.0
        return {
            "equity_now": float(now_eq),
            "equity_sod": float(sod),
            "pnl_today_abs": float(pnl_abs),
            "pnl_today_pct": float(pnl_pct),
        }
    except Exception as e:
        return {"equity_now": 0.0, "equity_sod": 0.0, "pnl_today_abs": 0.0, "pnl_today_pct": 0.0, "error": str(e)}


@app.get("/risk_profile")
def risk_profile():
    # Use the latest equity snapshot if available; else default to 1000
    try:
        series = load_equity_series(limit=1)
        eq = float(series[-1][1]) if series else 1000.0
    except Exception:
        eq = 1000.0
    prof = pick_profile(eq)
    return {
        "equity": eq,
        "profile": prof.name,
        "risk_multiplier": prof.risk_multiplier,
        "leverage_max": prof.leverage_max,
        "risk_per_trade_pct": prof.risk_per_trade_pct,
        "max_daily_loss_pct": prof.max_daily_loss_pct,
        "auto_flatten_on_dll": prof.auto_flatten_on_dll,
    }


@app.get("/diagnostics")
def diagnostics():
    env = {
        "AET_RUNTIME_DIR": os.getenv("AET_RUNTIME_DIR"),
        "AET_DB_PATH": os.getenv("AET_DB_PATH"),
        "SYMBOLS": os.getenv("SYMBOLS"),
        "MODE": os.getenv("MODE"),
        "TIMEFRAME": os.getenv("TIMEFRAME"),
    }
    # runtime files
    files = []
    if RUNTIME_DIR.exists():
        for p in sorted(RUNTIME_DIR.glob("*_runtime.json")):
            try:
                st = p.stat()
                files.append({"name": p.name, "size": st.st_size, "mtime": st.st_mtime})
            except Exception:
                continue
    acct = _load_account_runtime()
    acct_path = RUNTIME_DIR / "account_runtime.json"
    acct_stat = None
    if acct_path.exists():
        try:
            st = acct_path.stat()
            acct_stat = {"name": acct_path.name, "size": st.st_size, "mtime": st.st_mtime}
        except Exception:
            pass
    # DB info
    db_path = str(DB_PATH.resolve())
    db_last = None
    try:
        series = load_equity_series(limit=1)
        if series:
            db_last = float(series[-1][1])
    except Exception:
        pass
    trades_24h = None
    try:
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM trades WHERE datetime(entry_ts) >= datetime('now','-1 day')")
        row = cur.fetchone()
        trades_24h = int(row[0]) if row else 0
        con.close()
    except Exception:
        pass
    out = {
        "env": env,
        "runtime_dir": str(RUNTIME_DIR),
        "account_file": acct_stat,
        "symbol_runtime_files": files,
        "db_path": db_path,
        "db_last_equity": db_last,
        "trades_last_24h_db": trades_24h,
        "account_snapshot": acct,
    }
    try:
        now_ts = int(time.time())
        rows = fetch_recent_decisions(limit=1000)
        out["decisions_last_24h"] = sum(1 for r in rows if int(r.get("ts", 0)) >= now_ts - 86400)
    except Exception:
        out["decisions_last_24h"] = None
    return out


@app.get("/decisions_json")
def decisions_json(limit: int = 200):
    try:
        rows = fetch_recent_decisions(limit=limit)
        return {"count": len(rows), "items": rows}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/export/decisions.csv")
def export_decisions_csv(limit: int = 5000):
    import csv, io

    rows = fetch_recent_decisions(limit=limit)
    buf = io.StringIO()
    cols = (
        list(rows[0].keys())
        if rows
        else [
            "ts",
            "symbol",
            "strategy",
            "regime",
            "signal",
            "intent",
            "size_usd",
            "price",
            "ml_p_up",
            "ml_vote",
            "veto",
            "reasons",
            "planned_stop",
            "planned_tp",
            "run_id",
        ]
    )
    w = csv.DictWriter(buf, fieldnames=cols)
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return Response(content=buf.getvalue(), media_type="text/csv")


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

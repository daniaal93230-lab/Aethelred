"""
Visor: minimal truth UI for Aethelred

Env:
  VISOR_API_BASE   Base URL of the running API, default http://127.0.0.1:8080
Endpoints used:
  GET {VISOR_API_BASE}/healthz
  GET {VISOR_API_BASE}/runtime/account_runtime.json

Expected runtime/account_runtime.json shape (robust to missing keys):
{
  "heartbeat_ts": "2025-10-26T18:22:15.123Z",
  "equity": [
    {"ts": "2025-10-26T18:20:00Z", "equity": 100000.0},
    {"ts": "2025-10-26T18:21:00Z", "equity": 100250.4},
    ...
  ],
  "positions": [
    {
      "symbol": "BTCUSDT",
      "side": "LONG",
      "qty": 0.25,
      "entry": 64420.0,
      "mark": 64600.5,
      "unrealized_pct": 0.28
    },
    ...
  ]
}
"""

import os
import time
from typing import Any, Dict, List, Optional, cast

import pandas as pd
import requests  # type: ignore[import-untyped]
import streamlit as st


API_BASE = os.getenv("VISOR_API_BASE", "http://127.0.0.1:8080")
HEALTHZ_URL = f"{API_BASE}/healthz"
RUNTIME_URL = f"{API_BASE}/runtime/account_runtime.json"  # may 404 on some builds
METRICS_URL = f"{API_BASE}/metrics_json"  # fallback source for liveness/KPIs
REFRESH_SECS = int(os.getenv("VISOR_REFRESH_SECS", "2"))
TIMEOUT = float(os.getenv("VISOR_HTTP_TIMEOUT", "2.5"))


@st.cache_data(show_spinner=False, ttl=1.0)
def fetch_json(url: str, timeout: float = TIMEOUT) -> Optional[Dict[str, Any]]:
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        # r.json() is untyped; cast to the declared return type to satisfy strict mypy
        return cast(Optional[Dict[str, Any]], r.json())
    except Exception:
        return None


def parse_equity(runtime: Optional[Dict[str, Any]]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    if runtime and isinstance(runtime.get("equity"), list):
        for it in runtime["equity"]:
            ts = it.get("ts")
            eq = it.get("equity")
            if ts is None or eq is None:
                continue
            rows.append({"ts": ts, "equity": float(eq)})
    df = pd.DataFrame(rows)
    if not df.empty:
        # Try to parse timestamps, if parsing fails leave as string
        try:
            df["ts"] = pd.to_datetime(df["ts"], utc=True)
        except Exception:
            pass
        df = df.sort_values("ts")
    return df


def parse_positions(runtime: Optional[Dict[str, Any]]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    if runtime and isinstance(runtime.get("positions"), list):
        for p in runtime["positions"]:
            sel = p.get("selector") or {}
            strategy = sel.get("strategy_name") or p.get("strategy_name")
            rows.append(
                {
                    "symbol": p.get("symbol", ""),
                    "side": p.get("side", ""),
                    "qty": p.get("qty", 0),
                    "entry": p.get("entry", None),
                    "mark": p.get("mark", None),
                    "PnL%": p.get("unrealized_pct", None),
                    "strategy": strategy,
                }
            )
    df = pd.DataFrame(rows, columns=["symbol", "side", "qty", "entry", "mark", "PnL%", "strategy"])
    # Simple numeric cleanup
    for c in ["qty", "entry", "mark", "PnL%"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def breaker_chip(healthz: Optional[Dict[str, Any]]) -> str:
    """
    Render a tiny text chip from /healthz payload.
    Expected keys (best effort): status, breakers, kill_switch, last_heartbeat_ts
    """
    if not healthz:
        return "status: UNKNOWN"
    status = str(healthz.get("status", "unknown")).upper()
    # tolerate both root-level and nested engine keys
    kill = bool(healthz.get("kill_switch", False))
    daily = None
    # new shape seen: healthz["engine"]["breakers"]["daily_loss_tripped"]
    eng = healthz.get("engine") or {}
    b = (healthz.get("breakers") or {}) or eng.get("breakers") or {}
    if "daily_loss" in b:
        daily = bool(b.get("daily_loss"))
    elif "daily_loss_tripped" in b:
        daily = bool(b.get("daily_loss_tripped"))
    bits = [f"status: {status}"]
    if kill:
        bits.append("KILL=ON")
    if daily is True:
        bits.append("DAILY_BREAKER=TRIPPED")
    elif daily is False:
        bits.append("DAILY_BREAKER=OK")
    return " | ".join(bits)


def extract_kpis(healthz: Optional[Dict[str, Any]], runtime: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return {'realized_pnl_today_usd': float|None, 'trade_count_today': int|None} from either source."""
    out = {"realized_pnl_today_usd": None, "trade_count_today": None}
    if runtime:
        out["realized_pnl_today_usd"] = runtime.get("realized_pnl_today_usd", out["realized_pnl_today_usd"])
        out["trade_count_today"] = runtime.get("trade_count_today", out["trade_count_today"])
    if healthz:
        eng = healthz.get("engine") or {}
        for k in out.keys():
            if out[k] is None and k in eng:
                out[k] = eng.get(k)
    return out


def main() -> None:
    st.set_page_config(page_title="Aethelred Visor", layout="wide")
    st.markdown(
        "<h2 style='margin-bottom:0'>Aethelred Visor</h2>"
        "<div style='color:#777;margin-top:2px;'>Show the truth, simply</div>",
        unsafe_allow_html=True,
    )

    # Top bar with status
    cols = st.columns([3, 2, 2, 2])
    with cols[0]:
        st.caption(f"API: {API_BASE}")
    healthz = fetch_json(HEALTHZ_URL)
    runtime = fetch_json(RUNTIME_URL)
    # optional fallback: if runtime JSON is not served, try metrics to keep the page useful
    if not runtime:
        _metrics = fetch_json(METRICS_URL)  # not rendered directly, but proves API is alive
        if _metrics and isinstance(_metrics, dict):
            # metrics_json shape may carry small slices we can map into runtime for kpis
            runtime = runtime or {}
            # attach lightweight equity/positions if present
            if "positions" not in runtime and "positions" in _metrics:
                runtime["positions"] = _metrics.get("positions")
            if "equity" not in runtime and "equity" in _metrics:
                runtime["equity"] = _metrics.get("equity")

    with cols[1]:
        st.metric("Refresh", f"{REFRESH_SECS}s", help="Auto refresh cadence")
    with cols[2]:
        chip = breaker_chip(healthz)
        st.markdown(f"**Breaker**: {chip}")
    with cols[3]:
        hb = None
        # Prefer runtime heartbeat if present
        if runtime and runtime.get("heartbeat_ts"):
            hb = runtime.get("heartbeat_ts")
        elif healthz and healthz.get("last_heartbeat_ts"):
            hb = healthz.get("last_heartbeat_ts")
        st.markdown(f"**Last heartbeat**: {hb or 'unknown'}")

    # KPIs (realized PnL + trade count) using either runtime or healthz.engine
    kpis = extract_kpis(healthz, runtime)
    with cols[4] if len(cols) > 4 else st.container():
        st.metric("Realized PnL (today)", f"${kpis.get('realized_pnl_today_usd') or 0:.2f}")
        st.metric("Trades (today)", f"{kpis.get('trade_count_today') or 0}")

    st.divider()

    # Two panels: Equity curve and Open positions
    left, right = st.columns([2, 3], gap="large")

    with left:
        st.subheader("Equity")
        eq_df = parse_equity(runtime)
        if eq_df.empty:
            st.info("No equity data yet.")
        else:
            # Streamlit line_chart is simple and fast
            chart_df = eq_df.set_index("ts")[["equity"]]
            st.line_chart(chart_df, height=260)

    with right:
        st.subheader("Open positions")
        pos_df = parse_positions(runtime)
        if pos_df.empty:
            st.info("No open positions.")
        else:
            # Lightweight formatting
            fmt = pos_df.copy()
            if "PnL%" in fmt.columns:
                fmt["PnL%"] = fmt["PnL%"].map(lambda v: None if pd.isna(v) else round(v, 2))
            st.dataframe(
                fmt,
                use_container_width=True,
                hide_index=True,
            )

    # Auto refresh with core Streamlit only
    st.caption("Auto-refreshing...")
    time.sleep(REFRESH_SECS)
    st.rerun()


if __name__ == "__main__":
    main()

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from api.bootstrap_real_engine import services_or_none
import time

router = APIRouter()


@router.get("/ops", response_class=HTMLResponse)
async def ops_dashboard() -> HTMLResponse:
    """
    Lightweight Ops dashboard.
    No JS build step, safe in paper mode, and best-effort only.
    """
    sv = services_or_none()

    if sv is None:
        html = """
        <html>
          <head><title>Aethelred Ops</title></head>
          <body style="font-family: system-ui, sans-serif; padding: 1.5rem;">
            <h1>Aethelred Ops Panel</h1>
            <p>Status: <strong style="color: #c00;">Orchestrator not running</strong></p>
            <p>Tip: start the API with orchestrator lifespan enabled.</p>
          </body>
        </html>
        """
        return HTMLResponse(content=html)

    now = time.time()

    # best effort reads
    orch = getattr(sv, "multi_orch", None)
    symbols_data = {}
    portfolio = {}
    risk_off = False
    hard_dd = False

    try:
        if orch is not None:
            snap = orch.snapshot()
            symbols_data = snap.get("symbols", {})
            portfolio = snap.get("portfolio", {})
            risk_off = bool(getattr(orch, "global_risk_off", False))
    except Exception:
        pass

    try:
        # if orchestrator_v2 exposes kill flags
        hard_dd = bool(getattr(orch, "global_killed", False))
    except Exception:
        pass

    eq = portfolio.get("portfolio_equity", "n/a")
    realized = portfolio.get("total_realized_pnl", "n/a")
    unreal = portfolio.get("total_unrealized_pnl", "n/a")

    rows_html = ""
    for sym, s in symbols_data.items():
        exec_section = s.get("execution", {})
        last_sig = s.get("last_signal", "n/a")
        last_reg = s.get("last_regime", "n/a")
        eq_sym = exec_section.get("equity_now", "n/a")
        unreal_sym = exec_section.get("unrealized_pnl", "n/a")
        rows_html += f"""
          <tr>
            <td>{sym}</td>
            <td>{last_reg}</td>
            <td>{last_sig}</td>
            <td>{eq_sym}</td>
            <td>{unreal_sym}</td>
          </tr>
        """

    risk_badge = "OK"
    risk_color = "#0a0"
    if risk_off or hard_dd:
        risk_badge = "RISK-OFF"
        risk_color = "#c00"

    html = f"""
    <html>
      <head>
        <title>Aethelred Ops</title>
        <style>
          body {{
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            padding: 1.5rem;
            background: #0b1020;
            color: #f5f5f5;
          }}
          h1 {{
            margin-bottom: 0.5rem;
          }}
          .card {{
            background: #151b30;
            border-radius: 12px;
            padding: 1rem 1.25rem;
            margin-bottom: 1rem;
            box-shadow: 0 8px 20px rgba(0,0,0,0.35);
          }}
          table {{
            width: 100%%;
            border-collapse: collapse;
            margin-top: 0.5rem;
          }}
          th, td {{
            padding: 0.5rem;
            border-bottom: 1px solid #252b40;
            text-align: left;
            font-size: 0.9rem;
          }}
          th {{
            font-weight: 600;
          }}
          .badge {{
            display: inline-block;
            padding: 0.2rem 0.6rem;
            border-radius: 999px;
            font-size: 0.75rem;
            background: {risk_color};
            color: #fff;
          }}
          a {{
            color: #5cc9ff;
          }}
        </style>
      </head>
      <body>
        <h1>Aethelred Ops Panel</h1>
        <p>Now: {time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now))} UTC</p>

        <div class="card">
          <h2>Portfolio</h2>
          <p>Equity: <strong>{eq}</strong></p>
          <p>Realized PnL: <strong>{realized}</strong> &nbsp; | &nbsp; Unrealized PnL: <strong>{unreal}</strong></p>
          <p>Risk State: <span class="badge">{risk_badge}</span></p>
        </div>

        <div class="card">
          <h2>Per-Symbol Snapshot</h2>
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Regime</th>
                <th>Last Signal</th>
                <th>Equity</th>
                <th>Unrealized PnL</th>
              </tr>
            </thead>
            <tbody>
              {rows_html or '<tr><td colspan="5">No snapshots yet</td></tr>'}
            </tbody>
          </table>
        </div>

        <div class="card">
          <h2>Links</h2>
          <ul>
            <li><a href="/health">/health</a></li>
            <li><a href="/metrics">/metrics</a></li>
            <li><a href="/dashboard">/dashboard</a></li>
          </ul>
        </div>
      </body>
    </html>
    """

    return HTMLResponse(content=html)

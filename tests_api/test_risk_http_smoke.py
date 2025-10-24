from fastapi.testclient import TestClient
from api.main import app
from db.db_manager import insert_veto_log, ensure_veto_table

client = TestClient(app)


def test_metrics_json_has_risk_gauges():
    r = client.get("/metrics_json")
    assert r.status_code == 200
    data = r.json()
    assert "risk" in data
    risk = data["risk"]
    assert "kill_switch" in risk
    assert "per_trade_risk_pct" in risk
    assert "max_leverage" in risk
    assert "portfolio" in risk
    port = risk["portfolio"]
    for k in ["equity_now", "total_notional_usd", "max_exposure_usd", "leverage"]:
        assert k in port


def test_kill_switch_cycle_reflects_in_metrics():
    r1 = client.post("/risk/kill_switch/on")
    assert r1.status_code == 200
    assert r1.json().get("kill_switch") is True
    r2 = client.get("/metrics_json")
    assert r2.status_code == 200
    assert r2.json()["risk"]["kill_switch"] is True
    r3 = client.post("/risk/kill_switch/off")
    assert r3.status_code == 200
    assert r3.json().get("kill_switch") is False
    r4 = client.get("/metrics_json")
    assert r4.status_code == 200
    assert r4.json()["risk"]["kill_switch"] is False


def test_risk_config_endpoint_roundtrip():
    r = client.get("/risk/config")
    assert r.status_code == 200
    cfg = r.json()
    # basic required keys present
    assert "daily_loss_limit_pct" in cfg
    assert "per_trade_risk_pct" in cfg
    assert "max_leverage" in cfg
    assert "exposure" in cfg


def test_veto_stats_counts_from_seeded_logs():
    ensure_veto_table()
    insert_veto_log(
        {
            "symbol": "BTC/USDT",
            "side": "buy",
            "qty": 1.0,
            "notional": 100.0,
            "reason": "limit:per_symbol_exposure",
            "details": {"cap_usd": 2000.0},
        }
    )
    insert_veto_log(
        {
            "symbol": "ETH/USDT",
            "side": "sell",
            "qty": 2.0,
            "notional": 150.0,
            "reason": "limit:portfolio_exposure",
            "details": {"cap_usd": 3500.0},
        }
    )
    r = client.get("/risk/veto_stats?hours=48")
    assert r.status_code == 200
    body = r.json()
    assert body.get("hours") == 48
    counts = body.get("counts") or []
    assert isinstance(counts, list)
    reasons = {row["reason"]: int(row["n"]) for row in counts}
    # At least the two we inserted should be present
    assert "limit:per_symbol_exposure" in reasons
    assert "limit:portfolio_exposure" in reasons

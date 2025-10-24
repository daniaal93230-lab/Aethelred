from fastapi.testclient import TestClient
from api.app import app
from api.db_manager import get_conn

client = TestClient(app)


def _seed_trade():
    conn = get_conn()
    conn.execute(
        "insert into paper_trades(ts, symbol, side, qty, price, fee_usd, slippage_bps, pnl_usd, run_id) values(?,?,?,?,?,?,?,?,?)",
        (1.0, "BTC/USDT", "buy", 0.01, 25000.0, 0.05, 1.2, 0.0, "RUN_TEST"),
    )
    conn.commit()


def _seed_decision():
    conn = get_conn()
    conn.execute(
        "insert into decisions(ts, symbol, action, prob, veto, veto_reason, features_hash, run_id) values(?,?,?,?,?,?,?,?)",
        (1.0, "BTC/USDT", "buy", 0.55, 0, "", "abc123", "RUN_TEST"),
    )
    conn.commit()


def test_trades_csv_and_jsonl_endpoints():
    _seed_trade()
    r1 = client.get("/export/trades.csv")
    assert r1.status_code == 200
    assert "BTC/USDT" in r1.text
    r2 = client.get("/export/trades.jsonl")
    assert r2.status_code == 200
    assert "BTC/USDT" in r2.text


def test_decisions_csv_and_jsonl_endpoints():
    _seed_decision()
    assert client.get("/export/decisions.csv").status_code == 200
    assert client.get("/export/decisions.jsonl").status_code == 200

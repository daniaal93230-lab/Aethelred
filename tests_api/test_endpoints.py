# tests_api/test_endpoints.py
import io
import csv
import sqlite3
import datetime as dt

import pytest
from fastapi.testclient import TestClient

# Import your API app
import api.main as api_main


@pytest.fixture(scope="session")
def client(tmp_path_factory):
    # Prepare a temp DB with a minimal trades table and 1 row
    tmp_dir = tmp_path_factory.mktemp("aethelred_tests")
    db_path = tmp_dir / "aethelred.db"
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute(
        """
        create table if not exists trades (
            ts text not null,
            symbol text not null,
            side text not null,
            qty real not null,
            price real not null,
            fees real default 0.0,
            pnl real default 0.0,
            order_id text,
            status text not null
        )
        """
    )
    cur.execute(
        """
        insert into trades (ts, symbol, side, qty, price, fees, pnl, order_id, status)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2025-10-16T12:00:00Z",
            "BTC/USDT",
            "buy",
            0.01,
            65000.0,
            0.5,
            0.0,
            "oid-123",
            "filled",
        ),
    )
    con.commit()
    con.close()

    # Point the API to our temp DB and set a heartbeat
    api_main.DB_PATH = db_path
    api_main.LAST_HEARTBEAT["ts"] = dt.datetime(2025, 10, 16, 12, 5, 0).isoformat() + "Z"

    return TestClient(api_main.app)


def test_export_trades_csv_ok(client):
    r = client.get("/export/trades.csv")
    assert r.status_code == 200
    text = r.text.strip()
    # Validate CSV header and one row
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0] == [
        "ts",
        "symbol",
        "side",
        "qty",
        "price",
        "fees",
        "pnl",
        "order_id",
        "status",
    ]
    assert len(rows) == 2
    assert rows[1][1] == "BTC/USDT"
    assert rows[1][-1] == "filled"


def test_flatten_ok(client):
    r = client.post("/flatten", json={"mode": "paper", "reason": "test"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["result"]["mode"] == "paper"
    assert body["result"]["reason"] == "test"


def test_healthz_ok(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    snap = body["snapshot"]
    assert snap["db_present"] is True
    # Basic shape checks
    assert isinstance(snap["now_utc"], str)
    assert isinstance(snap["last_heartbeat"], str)


def test_ml_stop_distance_stubbed(client, monkeypatch):
    # Stub the loaded regressor object inside api.main
    class _StubReg:
        horizon_bars = 20
        fit_stats = {"mae": 0.10, "ece_pct": 2.1}

        def predict_atr_units(self, feats):
            # Ignore feats - return deterministic value for test
            return 1.23

    monkeypatch.setattr(api_main, "_sd", _StubReg(), raising=True)

    payload = {
        "symbol": "BTC/USDT",
        "features": {
            "atr14": 150.0,
            "atr28": 200.0,
            "std20": 0.01,
            "rng20": 100.0,
            "ret1": 0.0,
            "ret5": 0.0,
            "ema20slope": 0.0,
            "ema50slope": 0.0,
            "pos_dc20": 0.5,
            "volz20": 0.0,
            "tod_sin": 0.0,
            "tod_cos": 1.0,
            "dow_sin": 0.0,
            "dow_cos": 1.0,
            "atr_entry": 150.0,
            "side_sign": 1.0,
        },
    }
    r = client.post("/ml/stop_distance", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert abs(body["stop_atr"] - 1.23) < 1e-9
    assert body["horizon_bars"] == 20
    assert body["model_version"] == "stop_distance_regressor_v1"
    assert set(body["fit_stats"].keys()) == {"mae", "ece_pct"}

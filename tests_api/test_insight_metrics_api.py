import os
import sqlite3
from fastapi.testclient import TestClient

from api.main import app


def make_temp_db_with_fixture(tmp_path: str) -> str:
    db_path = os.path.join(tmp_path, "journal.db")
    conn = sqlite3.connect(db_path)
    try:
        root = os.path.dirname(os.path.dirname(__file__))
        fixture = os.path.join(root, "tests", "fixtures", "journal_sample.sql")
        # When running from repo root, adjust path
        if not os.path.exists(fixture):
            fixture = os.path.join(root, "fixtures", "journal_sample.sql")
        with open(fixture, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_insight_metrics_endpoint_returns_metrics(monkeypatch, tmp_path):
    db_path = make_temp_db_with_fixture(str(tmp_path))
    # Point the app to our temp DB
    setattr(app.state, "journal_db_path", db_path)

    client = TestClient(app)
    r = client.get("/insight/metrics")
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["ok"] is True
    assert "metrics" in payload
    m = payload["metrics"]
    # From the fixture we know win rate is 1 and expectancy is about 5 USD
    assert abs(m["expectancy_usd"] - 5.0) < 1e-9
    assert m["win_rate"] == 1.0

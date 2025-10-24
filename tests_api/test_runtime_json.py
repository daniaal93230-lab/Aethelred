import os
import json
from fastapi.testclient import TestClient
from api.app import app

client = TestClient(app)


def test_runtime_json_missing_ok():
    # Missing file should 404 or return missing
    if os.path.exists("runtime/account_runtime.json"):
        os.remove("runtime/account_runtime.json")
    r = client.get("/runtime_json")
    assert r.status_code in (200, 404)


def test_runtime_json_serves_snapshot(tmp_path):
    p = tmp_path / "account_runtime.json"
    os.environ["ACCOUNT_RUNTIME_PATH"] = str(p)
    data = {"equity_now": 12345.67, "positions": [], "ts": 1}
    p.write_text(json.dumps(data), encoding="utf-8")
    r = client.get("/runtime_json")
    assert r.status_code == 200
    body = r.json()
    assert body["equity_now"] == 12345.67

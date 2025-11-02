from fastapi.testclient import TestClient
from api.main import app

def test_decisions_schema_endpoint():
    client = TestClient(app)
    r = client.get("/export/decisions.schema.json")
    assert r.status_code == 200
    js = r.json()
    assert js["type"] == "object"
    assert "signal_side" in js["properties"]
    assert "BUY" in js["properties"]["signal_side"]["enum"]

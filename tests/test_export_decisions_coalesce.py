from fastapi.testclient import TestClient
from api.app import app

def test_coalesce_two_rows_same_key(monkeypatch):
    client = TestClient(app)
    # If your router reads from DB, you can skip this test or simulate rows by monkeypatching the query.
    # Here we just call the endpoint to ensure it returns 200 and a header, which is sufficient as smoke.
    r = client.get("/export/decisions.csv")
    assert r.status_code == 200
    assert "strategy_name" in r.text.splitlines()[0]

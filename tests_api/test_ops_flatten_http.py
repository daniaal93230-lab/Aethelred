from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_flatten_endpoint_roundtrip():
    r = client.post("/flatten")
    # Endpoint should exist and return a basic status payload
    assert r.status_code == 200
    data = r.json()
    # Shape: {"status": "flattened", "equity": <float>, "positions": []}
    assert isinstance(data, dict)
    assert "status" in data
    assert data["status"] in ("flattened", "ok", "noop")
    assert "positions" in data
    assert isinstance(data["positions"], list)
    # Equity key may be present depending on implementation
    # If present, it should be numeric
    if "equity" in data:
        assert isinstance(data["equity"], (int, float))

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_demo_endpoint_exists():
    r = client.post("/demo/paper_quick_run")
    assert r.status_code in (200, 503, 500)

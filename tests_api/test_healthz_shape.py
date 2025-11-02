from fastapi.testclient import TestClient
from api.main import app


class DummyEngine:
    def __init__(self):
        self.count = 2

    def heartbeat(self):
        return {"ok": True, "positions_count": self.count, "last_tick_ts": 123}

    def breakers_view(self):
        return {"kill_switch": False}

    def account_snapshot(self):
        return {"ts": 456}


def test_healthz_has_positions_and_last_ts():
    app.state.engine = DummyEngine()
    c = TestClient(app)
    r = c.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["engine"]["positions_count"] == 2
    assert body["engine"]["last_tick_ts"] == 123
    assert "breakers" in body["engine"]

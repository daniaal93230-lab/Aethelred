from fastapi.testclient import TestClient
from api.main import app


class DummyEngine:
    def __init__(self):
        self.flattened = 0
        self._breakers = {"kill_switch": False, "manual_breaker": False, "daily_loss_tripped": False}

    async def flatten_all(self, reason=""):
        self.flattened += 1
        return {"reason": reason}

    def heartbeat(self):
        return {"ok": True, "ts": 123, "positions": 0}

    def breakers_view(self):
        return dict(self._breakers)

    def breakers_set(self, **kwargs):
        for k, v in kwargs.items():
            if v is not None and k in self._breakers:
                self._breakers[k] = bool(v)
        if kwargs.get("clear_daily_loss"):
            self._breakers["daily_loss_tripped"] = False
        return dict(self._breakers)


def test_health_and_flatten_and_breaker():
    app.state.engine = DummyEngine()
    c = TestClient(app)
    assert c.get("/healthz").status_code == 200
    assert c.post("/flatten").status_code == 200
    rb = c.get("/risk/breaker").json()["breakers"]
    assert rb["kill_switch"] is False
    rb2 = c.post("/risk/breaker", json={"kill_switch": True}).json()["breakers"]
    assert rb2["kill_switch"] is True

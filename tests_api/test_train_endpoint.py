from fastapi.testclient import TestClient
from api.main import app


class DummyEngine:
    def __init__(self):
        self.calls = []

    def enqueue_train(self, job: str, notes=None):
        self.calls.append(("enqueue_train", job, notes))
        return {"id": "TICKET-1", "job": job}


def test_post_train_enqueues_job():
    app.state.engine = DummyEngine()
    c = TestClient(app)
    r = c.post("/train", json={"job": "stop_distance_v1", "notes": "smoke"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["ticket"]["id"] == "TICKET-1"

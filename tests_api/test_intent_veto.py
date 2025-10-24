from fastapi.testclient import TestClient
import api.main as api_main
import pytest


@pytest.fixture(scope="module")
def client():
    return TestClient(api_main.app)


def test_intent_veto_endpoint_stub(monkeypatch, client):
    class _StubIV:
        horizon_bars = 20
        fit_stats = {"auroc": 0.66, "brier": 0.18, "ece_pct": 2.5}

        def predict_proba(self, feats):
            return 0.61

    monkeypatch.setattr(api_main, "_iv", _StubIV(), raising=True)
    payload = {
        "symbol": "BTC/USDT",
        "ts": "2025-10-17T10:00:00Z",
        "features": {"atr14": 100.0, "ret1": 0.0},
    }
    r = client.post("/ml/intent_veto", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "allow"
    assert 0.0 <= body["p_good"] <= 1.0
    assert set(body["fit_stats"].keys()) == {"auroc", "brier", "ece_pct"}


def test_intent_veto_threshold_override(monkeypatch, client):
    class _StubIV2:
        fit_stats = {"auroc": 0.7, "brier": 0.17, "ece_pct": 2.0}

        def predict_proba(self, feats):
            return 0.40

    monkeypatch.setattr(api_main, "_iv", _StubIV2(), raising=True)
    r = client.post(
        "/ml/intent_veto",
        json={"symbol": "ETH/USDT", "ts": "2025-10-17T10:05:00Z", "features": {}, "threshold": 0.5},
    )
    assert r.status_code == 200
    assert r.json()["decision"] == "veto"

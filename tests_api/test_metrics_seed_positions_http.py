from typing import Any, Dict, List
from fastapi.testclient import TestClient
import api.main as mainmod
from api.main import app

client = TestClient(app)


def _seed_positions_monkeypatch() -> None:
    """
    Make /metrics_json see a nonzero total_notional_usd without touching the DB.
    We monkeypatch the imported get_positions symbol inside api.main.
    """

    def fake_get_positions() -> List[Dict[str, Any]]:
        return [
            {"symbol": "BTC/USDT", "qty": 0.01, "notional_usd": 260.0},
            {"symbol": "ETH/USDT", "qty": -0.02, "notional_usd": 60.0},
        ]

    mainmod.get_positions = fake_get_positions  # type: ignore[assignment]


def test_metrics_json_reflects_seeded_positions_notional():
    # First measure current value
    r0 = client.get("/metrics_json")
    assert r0.status_code == 200
    r0.json()  # ensure endpoint works; base value not used
    # Seed positions via monkeypatch
    _seed_positions_monkeypatch()
    r1 = client.get("/metrics_json")
    assert r1.status_code == 200
    data = r1.json()
    risk = data.get("risk", {})
    port = risk.get("portfolio", {})
    assert "total_notional_usd" in port
    seeded_total = float(port["total_notional_usd"])
    assert seeded_total >= 320.0  # 260 + 60
    # And it should be different from the base total in typical cases
    # If base already had notional, at least ensure seeded_total is not zero
    assert seeded_total != 0.0

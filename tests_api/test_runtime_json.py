import json
from pathlib import Path
from utils.snapshot import write_runtime_snapshot


class DummyEngine:
    def account_snapshot(self):
        return {
            "ts": 123,
            "equity_now": 1000.0,
            "total_notional_usd": 0.0,
            "positions": [{"symbol": "BTCUSDT", "qty": 0.1, "entry": 100.0, "side": "long", "mark": 101.0}],
        }


def test_runtime_json_written(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # prefer engine-backed call
    write_runtime_snapshot(DummyEngine())
    data = json.loads(Path("account_runtime.json").read_text())
    assert "equity_now" in data
    assert "positions" in data
    # mtm percent should be present for long: (101-100)/100 * 100 = 1.0
    assert data["positions"][0]["mtm_pnl_pct"] in (1.0, 1.0000)

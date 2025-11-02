from pathlib import Path
import json
from utils.snapshot import write_runtime_snapshot


class Eng:
    def realized_pnl_today_usd(self):
        return 12.5

    def trade_count_today(self):
        return 3

    def account_snapshot(self):
        return {"ts": 111, "equity_now": 1000, "total_notional_usd": 10, "positions": []}


def test_snapshot_includes_realized_and_count(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_runtime_snapshot(Eng())
    data = json.loads(Path("account_runtime.json").read_text())
    assert data["realized_pnl_today_usd"] == 12.5
    assert data["trade_count_today"] == 3

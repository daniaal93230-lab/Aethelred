import os
import sqlite3
from analytics.metrics import compute_all_metrics, reconstruct_round_trips

ROOT = os.path.dirname(os.path.dirname(__file__))

def load_fixture() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    # The fixture references other SQL files using the sqlite3 CLI `.read` directive.
    # Read and concatenate the referenced SQL files so executescript() can run them in-memory.
    base = os.path.join(ROOT, "fixtures")
    fixture_path = os.path.join(base, "journal_sample.sql")
    script_parts = []
    with open(fixture_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.strip().startswith(".read"):
                # .read <path> -> include content of referenced file
                parts = line.split(None, 1)
                if len(parts) == 2:
                    ref = parts[1].strip()
                    # Resolve relative references against repository root
                    if os.path.isabs(ref):
                        ref_path = ref
                    else:
                        ref_path = os.path.join(ROOT, ref)
                    if not os.path.exists(ref_path):
                        # try without leading slash
                        ref_path = os.path.join(ROOT, ref.lstrip("/\\"))
                    with open(ref_path, "r", encoding="utf-8") as rf:
                        script_parts.append(rf.read())
                continue
            script_parts.append(line + "\n")

    conn.executescript("\n".join(script_parts))
    return conn

def test_replay_consistency():
    conn = load_fixture()
    trades = reconstruct_round_trips(conn)
    assert len(trades) == 1
    t = trades[0]
    assert t.symbol == "BTCUSDT"
    assert t.side == "long"
    assert abs(t.entry_price - 60000.0) < 1e-9
    assert abs(t.exit_price - 60600.0) < 1e-9
    # profit before fees: 0.01 * 600 = 6.0 USD
    # fees total = 1.0 USD, net = 5.0 USD
    gross_usd = (t.exit_price - t.entry_price) * t.qty
    assert abs(gross_usd - 6.0) < 1e-9
    assert abs(t.fees_usd - 1.0) < 1e-9

    m = compute_all_metrics(conn)
    # Daily return day1: (100060 - 100000) / 100000 = 0.0006
    # Sharpe undefined with single return, we accept 0.0 due to stdev 0 handling
    assert m["sharpe"] == 0.0
    assert m["sortino"] == 0.0
    assert m["max_drawdown_pct"] == 0.0
    assert m["win_rate"] == 1.0
    assert abs(m["expectancy_usd"] - 5.0) < 1e-9

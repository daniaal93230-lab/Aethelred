import os
import sqlite3
from analytics.metrics import compute_all_metrics, reconstruct_round_trips

# Use the tests directory as the base for fixtures so CI runners find them
ROOT = os.path.dirname(__file__)

def load_fixture() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    # The fixture references other SQL files using the sqlite3 CLI `.read` directive.
    # Read and concatenate the referenced SQL files so executescript() can run them in-memory.
    # Try a set of candidate locations so CI environments with different cwd layouts work
    candidates = [
        os.path.join(ROOT, "fixtures", "journal_sample.sql"),
        os.path.join(os.getcwd(), "tests", "fixtures", "journal_sample.sql"),
        os.path.join(os.getcwd(), "fixtures", "journal_sample.sql"),
        os.path.join(os.path.dirname(ROOT), "fixtures", "journal_sample.sql"),
        os.path.join(os.getenv("GITHUB_WORKSPACE", ""), "tests", "fixtures", "journal_sample.sql"),
        os.path.join(os.getenv("GITHUB_WORKSPACE", ""), "fixtures", "journal_sample.sql"),
    ]
    fixture_path = None
    for c in candidates:
        if c and os.path.exists(c):
            fixture_path = c
            break
    if fixture_path is None:
        raise FileNotFoundError(f"Could not locate journal_sample.sql in candidates: {candidates}")
    script_parts = []
    with open(fixture_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.strip().startswith(".read"):
                # .read <path> -> include content of referenced file
                parts = line.split(None, 1)
                if len(parts) == 2:
                    ref = parts[1].strip()
                    # Resolve relative references against tests dir first, then repo root
                    repo_root = os.path.dirname(ROOT)
                    # Candidate resolution order for referenced files
                    ref_candidates = []
                    if os.path.isabs(ref):
                        ref_candidates.append(ref)
                    # relative to tests dir
                    ref_candidates.append(os.path.join(ROOT, ref))
                    # relative to cwd/tests
                    ref_candidates.append(os.path.join(os.getcwd(), ref))
                    # relative to repo root
                    ref_candidates.append(os.path.join(repo_root, ref.lstrip("/\\")))
                    # relative to GITHUB_WORKSPACE if present
                    gw = os.getenv("GITHUB_WORKSPACE", "")
                    if gw:
                        ref_candidates.append(os.path.join(gw, ref.lstrip("/\\")))

                    ref_path = None
                    for rc in ref_candidates:
                        if rc and os.path.exists(rc):
                            ref_path = rc
                            break
                    if ref_path is None:
                        raise FileNotFoundError(f"Referenced SQL file not found: {ref} (tried {ref_candidates})")
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

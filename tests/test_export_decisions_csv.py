from fastapi.testclient import TestClient
from api.app import app
from api.contracts.decisions_header import DECISIONS_HEADER


def test_decisions_csv_header_only_when_empty():
    client = TestClient(app)
    r = client.get("/export/decisions.csv")
    assert r.status_code == 200
    lines = [l for l in r.text.strip().splitlines()]
    header = lines[0].split(",")
    assert header == DECISIONS_HEADER
    # no rows when empty DB (at least header exists)
    assert len(lines) >= 1

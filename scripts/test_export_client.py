import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from fastapi.testclient import TestClient  # noqa: E402
from api.main import app  # noqa: E402

client = TestClient(app)

r = client.get("/export/trades.csv")
out = Path("exports_download")
out.mkdir(exist_ok=True)
open(out / "server_trades_client.csv", "wb").write(r.content)
print("status", r.status_code, "len", len(r.content))

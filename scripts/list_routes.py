from pathlib import Path
import sys

# Allow running this script from the repo scripts/ dir by adding project root
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from api.main import app  # noqa: E402

print("Registered routes:")
for r in app.routes:
    print(r.path)

from api.routes import runtime
from types import SimpleNamespace
from ops.qa_dev_engine import QADevEngine
import json

app = SimpleNamespace(state=SimpleNamespace(engine=QADevEngine()))
req = SimpleNamespace(app=app)

try:
    out = runtime.account_runtime(req)
    print("OK")
    print(json.dumps(out, indent=2))
except Exception:
    import traceback

    traceback.print_exc()

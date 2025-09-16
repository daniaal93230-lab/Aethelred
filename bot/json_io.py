try:
    from core.json_io import *  # re-export
except ImportError:
    import json
    def emit_signal_to_json(decision: dict, path: str, user=None, equity_curve=None, paper_summary=None):
        payload = {"decision": decision}
        if user is not None:
            payload["user"] = user
        if equity_curve is not None:
            try:
                payload["equity_curve"] = [(str(ts), float(val)) for ts, val in equity_curve.items()]
            except Exception:
                pass
        if paper_summary is not None:
            payload["paper_summary"] = paper_summary
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

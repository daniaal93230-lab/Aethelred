import json
from core.ml.explain import ExplainabilityEngine


def test_shap_json_fallback_no_model():
    """
    If SHAP or model missing, explanation should return neutral 0s.
    """
    expl = ExplainabilityEngine()
    out = expl.explain_json({"signal_strength": 1})

    assert isinstance(out, dict)
    assert all(v == 0.0 for v in out.values())


def test_shap_json_runs_with_minimal_data():
    """
    Even if incomplete data passed, extractor produces valid features.
    """
    expl = ExplainabilityEngine()
    out = expl.explain_json({
        "signal_strength": 0.5,
        "regime": "trend"
    })

    assert isinstance(out, dict)
    assert len(out) > 0


def test_endpoint_missing_snapshot_returns_404():
    """
    Endpoint must handle missing runtime snapshots safely.
    """
    from fastapi.testclient import TestClient
    from api.app import create_app

    app = create_app()
    client = TestClient(app)

    r = client.get("/ml/explain_signal/DOES_NOT_EXIST")
    assert r.status_code == 404

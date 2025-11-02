import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Local imports
from ml.train_intent_veto import train_intent_veto
from ml.feature_pipeline import build_features
from core.ml_gate import IntentVetoGate

try:
    # FastAPI TestClient for the /train endpoint test
    from fastapi.testclient import TestClient
    from api.main import app

    HAS_API = True
except Exception:
    HAS_API = False


def _make_trending_candles(n: int = 400, seed: int = 7) -> pd.DataFrame:
    """
    Create a gently trending price series with noise so labels are not degenerate.
    """
    rng = np.random.default_rng(seed)
    # pretend minutes over a day scale (unused variable removed)
    drift = 0.0008  # small positive drift
    noise = rng.normal(0.0, 0.002, size=n)
    ret = drift + noise
    price = 100.0 * np.exp(np.cumsum(ret))
    high = price * (1.0 + np.abs(rng.normal(0.0008, 0.0008, size=n)))
    low = price * (1.0 - np.abs(rng.normal(0.0008, 0.0008, size=n)))
    open_ = np.concatenate([[price[0]], price[:-1]])
    volume = rng.integers(100, 1000, size=n).astype(float)
    ts = np.arange(n) * 60  # seconds grid
    candles = pd.DataFrame(
        {
            "ts": ts,
            "open": open_,
            "high": high,
            "low": low,
            "close": price,
            "volume": volume,
            "symbol": "BTCUSDT",
        }
    )
    return candles


def _make_signals_from_momentum(candles: pd.DataFrame, every: int = 10) -> pd.DataFrame:
    """
    Generate simple raw signals based on short minus long momentum and sample 1 per `every` bars.
    Side is +1 when fast momentum > slow, else -1.
    """
    close = candles["close"].astype(float)
    fast = close.pct_change().rolling(5, min_periods=1).mean()
    slow = close.pct_change().rolling(20, min_periods=1).mean()
    side = np.where((fast - slow).fillna(0.0) > 0.0, 1, -1)
    sig = candles.loc[::every, ["ts", "symbol"]].copy()
    sig["side"] = side[::every]
    return sig.reset_index(drop=True)


def _write_csv(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path


def test_train_artifacts_and_metrics(tmp_path: Path):
    """
    End to end: build synthetic candles and signals, train, and verify artifacts and metrics shape.
    """
    candles = _make_trending_candles(n=360)
    signals = _make_signals_from_momentum(candles, every=8)

    candles_csv = _write_csv(candles, tmp_path / "candles.csv")
    signals_csv = _write_csv(signals, tmp_path / "signals.csv")

    outdir = tmp_path / "models" / "intent_veto"
    res = train_intent_veto(
        signals_csv=signals_csv,
        candles_csv=candles_csv,
        artifacts_dir=outdir,
        horizon=12,
        symbol="BTCUSDT",
    )
    # Artifacts exist
    assert (outdir / "model.pkl").exists()
    meta_path = Path(res["meta_path"])
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text())
    # Threshold sanity
    assert 0.0 < float(meta["decision_threshold"]) < 1.0
    # Validation metrics present and finite
    v = meta["validation"]
    assert all(k in v for k in ["ece", "precision", "recall"])
    assert 0.0 <= float(v["ece"]) < 0.5


def test_inference_gate_predicts_probabilities(tmp_path: Path):
    """
    Load the trained model with IntentVetoGate and ensure probabilities and decisions are valid.
    """
    candles = _make_trending_candles(n=240)
    signals = _make_signals_from_momentum(candles, every=6)
    candles_csv = _write_csv(candles, tmp_path / "candles.csv")
    signals_csv = _write_csv(signals, tmp_path / "signals.csv")
    outdir = tmp_path / "models" / "intent_veto"
    train_intent_veto(signals_csv, candles_csv, outdir, horizon=10, symbol="BTCUSDT")

    # Build a small feature slice aligned to a few latest candles
    X, _ = build_features(candles[["ts", "open", "high", "low", "close"]].tail(32))
    gate = IntentVetoGate(model_dir=outdir)
    prob = gate.predict_proba(X.to_numpy())
    assert prob.shape[0] == X.shape[0]
    assert np.all(prob >= 0.0) and np.all(prob <= 1.0)
    decisions = gate.allow(X.to_numpy())
    assert set(np.unique(decisions)).issubset({0, 1})


@pytest.mark.skipif(not HAS_API, reason="API not available in this environment")
def test_api_train_endpoint(tmp_path: Path):
    """
    Smoke test for POST /train using TestClient. Ensures 200 and artifact keys present.
    """
    candles = _make_trending_candles(n=240)
    signals = _make_signals_from_momentum(candles, every=6)
    candles_csv = _write_csv(candles, tmp_path / "candles.csv")
    signals_csv = _write_csv(signals, tmp_path / "signals.csv")

    client = TestClient(app)
    payload = {
        "signals_csv": str(signals_csv),
        "candles_csv": str(candles_csv),
        "horizon": 10,
        "symbol": "BTCUSDT",
    }
    r = client.post("/train", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    for k in ["status", "model_path", "meta_path", "validation", "threshold"]:
        assert k in data
    # Files exist
    assert Path(data["model_path"]).exists()
    assert Path(data["meta_path"]).exists()

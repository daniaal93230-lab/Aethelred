from __future__ import annotations
from pathlib import Path
from typing import Optional, Sequence
import joblib
import numpy as np
import pandas as pd

MODEL_PATH = Path("models") / "gate_logreg.joblib"
FEATURE_NAMES: Sequence[str] = ("ema12","ema26","ema_slope","rsi14","vol30")

def load_model(path: Path = MODEL_PATH):
    if not path.exists():
        return None
    return joblib.load(path)

def predict_p_up(model, feats_last: pd.Series) -> Optional[float]:
    """
    Expect model with sklearn .predict_proba and feats_last containing FEATURE_NAMES.
    Returns proba of 'up' (class 1), or None on failure.
    """
    try:
        x = np.array([feats_last.reindex(FEATURE_NAMES).astype(float).values], dtype=float)
        proba = model.predict_proba(x)[0]
        # assume classes [0:down, 1:up]
        return float(proba[1])
    except Exception:
        return None

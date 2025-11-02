from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any
import numpy as np
import joblib


class IntentVetoGate:
    """
    Loads calibrated model and meta. Call .allow(prob_inputs) to get gate decision.
    """
    def __init__(self, model_dir: Path = Path("models/intent_veto")):
        self.model_dir = model_dir
        self.model = None
        self.meta = None
        self._load()

    def _load(self):
        model_path = self.model_dir / "model.pkl"
        meta_path = self.model_dir / "model_meta.json"
        if model_path.exists():
            self.model = joblib.load(model_path)
        if meta_path.exists():
            self.meta = json.loads(meta_path.read_text())

    @property
    def threshold(self) -> float:
        if self.meta and "decision_threshold" in self.meta:
            return float(self.meta["decision_threshold"])
        return 0.5

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if self.model is None:
            # Safe default: no veto if model missing
            return np.full((X.shape[0],), 1.0)
        prob = self.model.predict_proba(X)[:, 1]
        return prob

    def allow(self, X: np.ndarray) -> np.ndarray:
        prob = self.predict_proba(X)
        t = self.threshold
        return (prob >= t).astype(int)

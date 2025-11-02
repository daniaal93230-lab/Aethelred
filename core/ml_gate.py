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
    def model_version(self) -> str:
        if self.meta and "validation" in self.meta:
            # Use checksum surrogate for version traceability
            return f"v-{abs(hash(json.dumps(self.meta, sort_keys=True))) % (10**8)}"
        return "v-none"

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
        decision = (prob >= t).astype(int)
        # Log each batch decision with version tag
        print(f"[MLGate] decision batch {len(decision)} using {self.model_version}, thr={t:.3f}")
        return decision

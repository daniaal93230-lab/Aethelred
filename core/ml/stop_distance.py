# core/ml/stop_distance.py
from __future__ import annotations
import joblib, numpy as np
from pathlib import Path
from typing import Dict, Any


class StopDistanceRegressor:
    def __init__(self, path: str | Path):
        pkg = joblib.load(path)
        self.model = pkg["sk_model"]
        self.calib = pkg["calibrator"]
        self.cols = pkg["feature_cols"]
        self.horizon_bars = pkg.get("horizon_bars", 20)
        self.fit_stats = pkg.get("fit_stats", {})

    def features_from_row(self, row: Dict[str, Any]) -> np.ndarray:
        return np.array([row.get(c, np.nan) for c in self.cols], dtype=float)

    def predict_atr_units(self, feats_row: Dict[str, Any]) -> float:
        x = self.features_from_row(feats_row).reshape(1, -1)
        raw = float(self.model.predict(x)[0])
        return float(self.calib.transform([raw])[0])

from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, cast
import numpy as np
from joblib import load


class IntentVeto:
    def __init__(self, path: str | Path) -> None:
        # joblib.load may return untyped structures; cast to a typed dict
        pkg = cast(Dict[str, Any], load(path))
        self.clf = pkg["clf"]
        self.cal = pkg["cal"]
        self.cols = pkg["feature_cols"]
        self.horizon_bars = pkg.get("horizon_bars", 20)
        self.fit_stats = pkg.get("fit_stats", {})

    def _row_to_array(self, feats: Dict[str, Any]) -> np.ndarray:
        return np.array([feats.get(c, np.nan) for c in self.cols], dtype=float).reshape(1, -1)

    def predict_proba(self, feats: Dict[str, Any]) -> float:
        x = self._row_to_array(feats)
        return float(self.cal.predict_proba(x)[:, 1][0])

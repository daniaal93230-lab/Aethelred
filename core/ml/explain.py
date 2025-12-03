"""
SHAP Explainability Helper for the Meta-Signal Ranker.

Produces:
  - JSON {feature_name: shap_value}
  - Bar plot (returned as base64 PNG)

Gracefully degrades if:
  - SHAP library missing
  - Model missing
  - Feature vector missing
"""

from __future__ import annotations

import base64
import io
from typing import Dict, List, Any

from utils.logger import logger
from core.ml import MetaSignalFeatureExtractor, get_ranker


class ExplainabilityEngine:
    def __init__(self) -> None:
        self.extractor = MetaSignalFeatureExtractor()
        self.ranker = get_ranker()

        try:
            import shap  # type: ignore
            self._shap = shap
        except Exception:
            self._shap = None
            logger.warning("ExplainabilityEngine: SHAP unavailable. Using fallback.")

    # -----------------------------------------------------------
    # Core API
    # -----------------------------------------------------------
    def explain_json(self, data: Dict[str, Any]) -> Dict[str, float]:
        features = self.extractor.extract(data)
        booster = self.ranker.model

        if booster is None or self._shap is None:
            # Fallback explanation = neutral contributions
            return {name: 0.0 for name in self.extractor.FEATURE_ORDER}

        try:
            explainer = self._shap.TreeExplainer(booster)
            shap_vals = explainer.shap_values([features])[0]

            return {
                name: float(val)
                for name, val in zip(self.extractor.FEATURE_ORDER, shap_vals)
            }
        except Exception as e:
            logger.error(f"ExplainabilityEngine: SHAP JSON failed: {e}")
            return {name: 0.0 for name in self.extractor.FEATURE_ORDER}

    # -----------------------------------------------------------
    # Bar Chart mode → returns base64 encoded PNG
    # -----------------------------------------------------------
    def explain_plot(self, data: Dict[str, Any]) -> str:
        features = self.extractor.extract(data)
        booster = self.ranker.model

        if booster is None or self._shap is None:
            return ""

        try:
            explainer = self._shap.TreeExplainer(booster)
            shap_vals = explainer.shap_values([features])[0]

            fig = self._shap.plots._waterfall.waterfall_legacy(
                self.extractor.FEATURE_ORDER,
                shap_vals
            )

            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
            buf.seek(0)
            return base64.b64encode(buf.getvalue()).decode("utf-8")

        except Exception as e:
            logger.error(f"ExplainabilityEngine: SHAP plot failed: {e}")
            return ""

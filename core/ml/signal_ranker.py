"""
XGBoost Meta-Signal Ranker (v1)

Responsibilities:
  - Load /models/signal_ranker.json
  - Validate checksum (optional)
  - Score feature vectors produced by MetaSignalFeatureExtractor
  - Provide PAPER-safe fallback when model missing
  - Never crash at runtime

The ExecutionEngine integration and veto/downscale logic is added in Batch 4.C.
"""

from __future__ import annotations

import json
import os
import hashlib
from typing import Any, List, Optional

from utils.logger import logger


MODEL_PATH = "models/signal_ranker.json"
META_PATH = "models/signal_ranker.meta.json"


class SignalRanker:
    """
    Lightweight wrapper around an XGBoost Booster object.
    Provides:
        - load()
        - score(features)
        - safe fallback if model missing
    """

    def __init__(self) -> None:
        self.model: Optional[Any] = None
        self.loaded: bool = False
        self.model_version: str = "unknown"
        self.model_checksum: str = "unknown"

        # Lazy xgboost handle
        self._xgb = None

        self._load_if_exists()

    def _lazy_import_xgb(self):
        """Import xgboost only when actually needed."""
        if self._xgb is not None:
            return self._xgb
        try:
            import xgboost as xgb  # type: ignore
            self._xgb = xgb
            return xgb
        except Exception:
            logger.warning("SignalRanker: xgboost not available, running in fallback mode.")
            self._xgb = None
            return None

    # -------------------------
    # Loading / metadata
    # -------------------------

    def _load_if_exists(self) -> None:
        if not os.path.exists(MODEL_PATH):
            logger.warning("SignalRanker: model not found; running in fallback mode.")
            return

        try:
            xgb = self._lazy_import_xgb()
            if xgb is None:
                self.model = None
                self.loaded = False
                return
            self.model = xgb.Booster()
            self.model.load_model(MODEL_PATH)
            self.loaded = True
        except Exception as e:
            logger.error(f"SignalRanker: failed to load model: {e}")
            self.model = None
            self.loaded = False
            return

        # Load metadata if available
        if os.path.exists(META_PATH):
            try:
                with open(META_PATH, "r") as fh:
                    meta = json.load(fh)
                self.model_version = meta.get("version", "unknown")
                self.model_checksum = meta.get("checksum", "unknown")
            except Exception:
                pass
        else:
            # Auto-compute checksum
            self.model_checksum = self._compute_checksum()
            self.model_version = "unspecified"

        logger.info(
            f"SignalRanker: loaded model (version={self.model_version}, checksum={self.model_checksum})"
        )

    def _compute_checksum(self) -> str:
        try:
            h = hashlib.sha256()
            with open(MODEL_PATH, "rb") as fh:
                h.update(fh.read())
            return h.hexdigest()
        except Exception:
            return "unknown"

    # -------------------------
    # Scoring
    # -------------------------

    def score(self, features: List[float]) -> float:
        """
        Returns a score in [0, 1] or model-native score.

        If model is missing or errors, returns neutral score=0.5.
        Never crashes.
        """
        if not self.loaded or self.model is None:
            return 0.5

        try:
            # Need xgboost for scoring
            xgb = self._lazy_import_xgb()
            if xgb is None:
                return 0.5

            dmat = xgb.DMatrix([features])
            preds = self.model.predict(dmat)

            # If model outputs raw scores, clamp to [0, 1]
            if preds is None or len(preds) == 0:
                return 0.5

            score = float(preds[0])

            # Safety clamp
            if score < 0:
                return 0.0
            if score > 1:
                return 1.0
            return score

        except Exception as e:
            logger.error(f"SignalRanker: scoring error: {e}")
            return 0.5


# ------------------------------------------------------
# Standalone accessor (for DI / ExecutionEngine use)
# ------------------------------------------------------

_GLOBAL_RANKER: Optional[SignalRanker] = None


def get_ranker() -> SignalRanker:
    """
    Singleton accessor. Ensures:
      - one load per process
      - avoids repeated model parsing
    """
    global _GLOBAL_RANKER

    if _GLOBAL_RANKER is None:
        _GLOBAL_RANKER = SignalRanker()

    return _GLOBAL_RANKER

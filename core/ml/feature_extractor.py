"""
Meta-Signal Feature Extractor v1

Produces the canonical feature vector for the XGBoost Meta-Signal Ranker.
This module handles:
  - Decimal-safe conversions
  - Regime one-hot encoding
  - Strategy/indicator metadata
  - Volatility and structure metrics
  - Intent veto v2 passthrough

If any field is missing, the extractor fills with neutral defaults and logs no errors.
This ensures PAPER mode and unit tests never crash if the ML layer is absent.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, Any, Optional, List


# --------------------------
# Helpers
# --------------------------

def _dec(x: Any) -> float:
    """Convert Decimal or numeric to float for model input."""
    if isinstance(x, Decimal):
        return float(x)
    try:
        return float(x)
    except Exception:
        return 0.0


def _one_hot_regime(regime: Optional[str]) -> Dict[str, float]:
    """
    Regime categories (Phase 4 canonical):
      - trend
      - chop
      - transition
    """
    base = {
        "regime_trend": 0.0,
        "regime_chop": 0.0,
        "regime_transition": 0.0,
    }
    if not regime:
        return base

    r = regime.lower()
    if r in ("trend", "trending"):
        base["regime_trend"] = 1.0
    elif r in ("chop", "range", "ranging"):
        base["regime_chop"] = 1.0
    elif r in ("transition", "transitional"):
        base["regime_transition"] = 1.0

    return base


# --------------------------
# Feature Extractor
# --------------------------

class MetaSignalFeatureExtractor:
    """
    Canonical feature extractor for the XGBoost-based Meta-Signal Ranker.

    Input schema (dictionary):
        - signal_strength: Decimal/float
        - regime: str
        - volatility: dict with keys {"atr", "std", "zscore"} (optional)
        - donchian: dict {"upper", "lower", "width"} (optional)
        - ma: dict {"slope", "fast", "slow"} (optional)
        - rsi: dict {"value"} (optional)
        - intent_veto: dict {"prob"} (optional)

    Output:
        Ordered list[float] suitable for XGBoost ranker.
        Missing fields replaced with defaults.
    """

    FEATURE_ORDER: List[str] = [
        "signal_strength",
        # regime one-hot
        "regime_trend",
        "regime_chop",
        "regime_transition",
        # volatility
        "vol_atr",
        "vol_std",
        "vol_z",
        # donchian
        "donchian_width",
        # moving average structure
        "ma_slope",
        "ma_fast",
        "ma_slow",
        # rsi
        "rsi_value",
        # intent veto
        "intent_prob",
    ]

    def extract(self, data: Dict[str, Any]) -> List[float]:
        # --- Core signal strength
        sig = _dec(data.get("signal_strength", 0))

        # --- Regime OHE
        regime_ohe = _one_hot_regime(data.get("regime"))

        # --- Volatility metrics
        vol = data.get("volatility", {}) or {}
        vol_atr = _dec(vol.get("atr", 0))
        vol_std = _dec(vol.get("std", 0))
        vol_z = _dec(vol.get("zscore", 0))

        # --- Donchian width
        don = data.get("donchian", {}) or {}
        don_width = _dec(
            don.get("width")
            or (
                _dec(don.get("upper", 0)) - _dec(don.get("lower", 0))
                if don.get("upper") and don.get("lower")
                else 0
            )
        )

        # --- MA structure
        ma = data.get("ma", {}) or {}
        ma_slope = _dec(ma.get("slope", 0))
        ma_fast = _dec(ma.get("fast", 0))
        ma_slow = _dec(ma.get("slow", 0))

        # --- RSI
        rsi = data.get("rsi", {}) or {}
        rsi_value = _dec(rsi.get("value", 50))

        # --- Intent veto v2
        intent = data.get("intent_veto", {}) or {}
        intent_prob = _dec(intent.get("prob", 1))

        # Build final ordered vector
        features: Dict[str, float] = {
            "signal_strength": sig,
            **regime_ohe,
            "vol_atr": vol_atr,
            "vol_std": vol_std,
            "vol_z": vol_z,
            "donchian_width": don_width,
            "ma_slope": ma_slope,
            "ma_fast": ma_fast,
            "ma_slow": ma_slow,
            "rsi_value": rsi_value,
            "intent_prob": intent_prob,
        }

        # Produce list in canonical FEATURE_ORDER
        return [features[name] for name in self.FEATURE_ORDER]

"""
ML Meta-Signal Gate

Hybrid veto + probabilistic downscale logic.
Implements the rule:

  score < veto_threshold        → hard veto
  veto_threshold–down_low       → 30 percent size
  down_low–down_high            → 60 percent size
  ≥ down_high                   → 100 percent size

Configurable via config.env.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Tuple


def apply_ml_gate(
    score: float,
    base_size: Decimal,
    veto_threshold: float,
    down_low: float,
    down_high: float,
) -> Tuple[Decimal, bool, str]:
    """
    Returns:
        (new_size, veto_flag, action_label)
    """

    # Hard veto
    if score < veto_threshold:
        return Decimal("0"), True, "veto"

    # Tier 1 downscale
    if veto_threshold <= score < down_low:
        return (base_size * Decimal("0.30")).quantize(Decimal("0.00000001")), False, "downscale_30"

    # Tier 2 downscale
    if down_low <= score < down_high:
        return (base_size * Decimal("0.60")).quantize(Decimal("0.00000001")), False, "downscale_60"

    # Full size
    return base_size, False, "full"

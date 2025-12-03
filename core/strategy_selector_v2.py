"""
Strategy Selector V2 (Regime → Strategy Router)
------------------------------------------------

Implements:
 - ADX(14)-based regime classification
 - TTL-B (ATR-adaptive TTL)
 - Regime → strategy routing
 - Unified strategy API

Phase 4 Component (Strategos)
"""

from __future__ import annotations

from decimal import Decimal, getcontext
from typing import List, Dict, Any

getcontext().prec = 28


# ============================================================================
#  Utility indicators (local minimal versions)
# ============================================================================


def true_range(high: Decimal, low: Decimal, prev_close: Decimal) -> Decimal:
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Decimal:
    """Minimal ATR for TTL-B logic"""
    if len(highs) <= period:
        return Decimal("0")

    trs = []
    for i in range(1, len(highs)):
        h = Decimal(str(highs[i]))
        l = Decimal(str(lows[i]))
        pc = Decimal(str(closes[i - 1]))
        trs.append(true_range(h, l, pc))

    if len(trs) < period:
        return Decimal("0")

    avg = sum(trs[-period:]) / Decimal(str(period))
    return avg


def adx(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Decimal:
    """
    Minimal ADX implementation sufficient for regime classification.
    NOTE: This is intentionally lightweight for Phase 4.
    """
    n = len(highs)
    if n <= period + 1:
        return Decimal("0")

    # Convert to Decimal
    highs_d = [Decimal(str(x)) for x in highs]
    lows_d = [Decimal(str(x)) for x in lows]
    closes_d = [Decimal(str(x)) for x in closes]

    # Directional movement
    dm_pos = []
    dm_neg = []
    trs = []

    for i in range(1, n):
        up = highs_d[i] - highs_d[i - 1]
        down = lows_d[i - 1] - lows_d[i]
        tr = true_range(highs_d[i], lows_d[i], closes_d[i - 1])
        trs.append(tr)

        dm_pos.append(up if (up > down and up > 0) else Decimal("0"))
        dm_neg.append(down if (down > up and down > 0) else Decimal("0"))

    # Smooth TR, DM+
    tr14 = sum(trs[-period:])
    dm_pos14 = sum(dm_pos[-period:])
    dm_neg14 = sum(dm_neg[-period:])

    if tr14 == 0:
        return Decimal("0")

    di_pos = (dm_pos14 / tr14) * Decimal("100")
    di_neg = (dm_neg14 / tr14) * Decimal("100")

    dx = abs(di_pos - di_neg) / (di_pos + di_neg + Decimal("1e-9")) * Decimal("100")
    return dx  # minimal ADX approximation


# ============================================================================
#  Regime Detector
# ============================================================================


class RegimeDetectorV2:
    """
    Classifies market regime using ADX thresholds:

        ADX >= 25 → trending
        ADX <= 15 → ranging
        else     → transitional
    """

    def classify(self, highs: List[float], lows: List[float], closes: List[float]) -> str:
        adx_val = adx(highs, lows, closes, period=14)

        if adx_val >= Decimal("25"):
            return "trending"
        if adx_val <= Decimal("15"):
            return "ranging"
        return "transitional"


# ============================================================================
#  Strategy Selector with Adaptive TTL (TTL-B)
# ============================================================================


class StrategySelectorV2:
    """
    Takes regime classification + TTL-B logic and selects an appropriate strategy.

    API:
        selector.select(highs, lows, closes) -> {
            "regime": str,
            "signal": str,
            "strength": Decimal,
            "meta": dict
        }
    """

    def __init__(self):
        self.regime_detector = RegimeDetectorV2()

        # TTL-B parameters
        self.base_ttl = 2
        self.ttl_range = 5
        self.ttl_remaining = 0
        self.locked_regime = None

    # ----------------------------------------------------------------------
    # TTL-B Calculation
    # ----------------------------------------------------------------------

    def compute_ttl(self, highs: List[float], lows: List[float], closes: List[float]) -> int:
        if len(closes) < 15:
            return self.base_ttl

        atr_val = atr(highs, lows, closes, period=14)
        close = Decimal(str(closes[-1]))

        if close <= 0:
            return self.base_ttl

        atr_norm = atr_val / close
        atr_norm = max(Decimal("0"), min(atr_norm, Decimal("0.10")))

        ttl = self.base_ttl + int((atr_norm * self.ttl_range))
        return max(1, min(ttl, self.base_ttl + self.ttl_range))

    # ----------------------------------------------------------------------
    # Strategy Router
    # ----------------------------------------------------------------------

    def select(self, highs: List[float], lows: List[float], closes: List[float]) -> Dict[str, Any]:

        # Determine regime
        detected_regime = self.regime_detector.classify(highs, lows, closes)

        # TTL-B locking
        if self.ttl_remaining > 0 and self.locked_regime is not None:
            regime = self.locked_regime
            self.ttl_remaining -= 1
        else:
            regime = detected_regime
            self.locked_regime = detected_regime
            self.ttl_remaining = self.compute_ttl(highs, lows, closes)

        # Regime → Strategy mapping
        if regime == "trending":
            strategy_name = "donchian_breakout"
        elif regime == "ranging":
            strategy_name = "rsi_mean_revert"
        else:
            strategy_name = "ma_crossover"

        # Strategy outputs nothing here — routed by ExecutionEngine later
        return {
            "regime": regime,
            "strategy": strategy_name,
            "signal": "hold",
            "strength": Decimal("0"),
            "meta": {},
        }


# END MODULE

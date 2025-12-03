"""
Phase 6 Risk Engine V3 scaffold.

Volatility Targeting Engine added (Phase 6.B-2).

This module defines the base classes for:
    - Global exposure model
    - Volatility targeting
    - Position sizing V3
    - Risk telemetry

Logic is intentionally left minimal so tests are not affected.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, Optional, Any
import math


class ExposureModel:
    """
    Base class for cross symbol exposure calculations.
    Concrete logic will be implemented in Phase 6.B.
    """

    def compute_exposure(self, positions: Dict[str, Decimal]) -> Dict[str, Any]:
        """
        positions: symbol → notional exposure (positive or negative)

        Returns:
            {
              "symbol_exposure": {symbol: pct},
              "total_exposure": pct,
              "raw": positions
            }
        """

        # No positions → zeroed exposure map
        if not positions:
            return {
                "symbol_exposure": {},
                "total_exposure": Decimal("0"),
                "raw": {},
            }

        # Use absolute notional to calculate exposure contribution
        abs_values = {s: abs(v) for s, v in positions.items()}
        total_abs = sum(abs_values.values(), Decimal("0"))

        # Guard for division by zero (extremely rare)
        if total_abs == 0:
            return {
                "symbol_exposure": {s: Decimal("0") for s in positions},
                "total_exposure": Decimal("0"),
                "raw": positions,
            }

        # Per symbol exposure contribution
        symbol_pct = {
            s: (abs(v) / total_abs)
            for s, v in abs_values.items()
        }

        # Total exposure as fraction (sum of abs notionals normalised to 1)
        total_pct = Decimal("1")  # normalized portfolio exposure = 100 pct

        return {
            "symbol_exposure": symbol_pct,
            "total_exposure": total_pct,
            "raw": positions,
        }


class PositionSizerV3:
    """
    Base class for the sizing logic used by RiskEngineV3.
    """
    def compute_size(
        self,
        symbol: str,
        signal: Optional[str],
        volatility: Decimal,
        exposure_caps: Dict[str, Decimal],
        equity: Decimal,
        current_symbol_exposure: Decimal,
        panic: bool = False,
    ) -> Decimal:
        """
        Return an absolute notional position size (USD) for the symbol.

        Behavior:
          - Returns 0 for HOLD / no-signal
          - Baseline fraction of equity (1%) adjusted by volatility
          - Enforces portfolio-level and per-symbol caps provided via
            exposure_caps (keys: 'global_cap', 'symbol_cap' as fractions)

        The function is defensive and conservative — any error returns 0.
        """
        try:
            if signal is None or (isinstance(signal, str) and signal.upper() == "HOLD"):
                return Decimal("0")

            # Baseline fraction of equity
            base_frac = Decimal("0.010")

            # ----------------------------------------------------
            # Phase 6.F — Kill-Switch / Panic Mode
            # If panic is True, force size to zero
            try:
                if panic:
                    return Decimal("0")
            except Exception:
                pass

            # Volatility dampening (simple)
            try:
                if volatility and volatility > 0:
                    adj = Decimal("1") / (Decimal("1") + volatility)
                else:
                    adj = Decimal("1")
            except Exception:
                adj = Decimal("1")

            notional = (equity * base_frac) * adj

            # ----------------------------------------------------
            # 3. Exposure caps (portfolio + per-symbol)
            # ----------------------------------------------------
            try:
                max_global = exposure_caps.get("global_cap", None) if exposure_caps else None
                if max_global is not None:
                    gmax = equity * Decimal(str(max_global))
                    if notional > gmax:
                        notional = gmax

                max_symbol = exposure_caps.get("symbol_cap", None) if exposure_caps else None
                if max_symbol is not None:
                    smax = equity * Decimal(str(max_symbol))
                    # current_symbol_exposure is already in USD
                    headroom = max(Decimal("0"), smax - (current_symbol_exposure or Decimal("0")))
                    if notional > headroom:
                        notional = headroom
            except Exception:
                pass

            return max(Decimal("0"), notional)
        except Exception:
            return Decimal("0")


class VolatilityTargeter:
    """
    Realized volatility estimator + portfolio scaling for volatility targeting.

    Vol estimate:
        - Uses last N returns (default 20)
        - Computes stdev of log returns
        - Returns daily vol (not annualized)

    Scaling factor:
        target_vol / portfolio_vol
    """

    def __init__(self, window: int = 20):
        self.window = window

    def estimate_vol(self, symbol: str, prices: list[Decimal]) -> Decimal:
        try:
            if len(prices) < 2:
                return Decimal("0")

            # Compute log returns
            rets = []
            # we'll iterate from the tail backwards to get the most recent window
            n = min(len(prices) - 1, self.window)
            for i in range(1, n + 1):
                p1 = prices[-i - 1]
                p0 = prices[-i]
                try:
                    if p0 > 0 and p1 > 0:
                        ratio = p0 / p1
                        # Decimal may have ln() in newer Pythons; fallback to math.log
                        if hasattr(ratio, "ln"):
                            ret = ratio.ln()
                        else:
                            ret = Decimal(str(math.log(float(ratio))))
                        rets.append(Decimal(ret))
                except Exception:
                    continue

            if len(rets) < 2:
                return Decimal("0")

            # mean
            mean_ret = sum(rets, Decimal("0")) / Decimal(len(rets))

            # stdev (population)
            var = sum((r - mean_ret) ** 2 for r in rets) / Decimal(len(rets))
            sd = var.sqrt()

            return sd
        except Exception:
            return Decimal("0")

    def scaling_factor(self, portfolio_vol: Decimal, target_vol: Decimal) -> Decimal:
        try:
            if portfolio_vol <= 0:
                return Decimal("1")
            return max(Decimal("0"), min(Decimal("5"), target_vol / portfolio_vol))
        except Exception:
            return Decimal("1")


class RiskTelemetry:
    """
    Collect telemetry values and expose them to orchestrator and metrics.
    Placeholder values only.
    """

    def __init__(self) -> None:
        # Defaults
        self.last_total_exposure: Decimal = Decimal("0")
        self.last_symbol_exposure: Dict[str, Decimal] = {}
        self.last_vol: Decimal = Decimal("0")
        self.last_portfolio_vol: Decimal = Decimal("0")
        self.last_scaling: Decimal = Decimal("1")
        # kill-switch / panic flag
        self.last_panic: bool = False

    def snapshot(self) -> Dict[str, Any]:
        snap = {}
        snap["total_exposure"] = self.last_total_exposure
        snap["symbol_exposure"] = self.last_symbol_exposure
        snap["volatility"] = self.last_vol
        snap["portfolio_vol"] = self.last_portfolio_vol
        snap["scaling_factor"] = self.last_scaling
        snap["panic"] = getattr(self, "last_panic", False)
        snap["status"] = "ok"
        return snap


class RiskEngineV3:
    """
    Main entry point for Phase 6 risk engine.
    This class is designed to be non intrusive until full logic is added.
    """

    def __init__(
        self,
        exposure_model: Optional[ExposureModel] = None,
        vol_targeter: Optional[VolatilityTargeter] = None,
        sizer: Optional[PositionSizerV3] = None,
        telemetry: Optional[RiskTelemetry] = None,
    ):
        self.exposure_model = exposure_model or ExposureModel()
        self.vol_targeter = vol_targeter or VolatilityTargeter()
        self.sizer = sizer or PositionSizerV3()
        self.telemetry = telemetry or RiskTelemetry()
        # symbol → cap fraction (phase 6 will populate)
        self.exposure_caps: Dict[str, Decimal] = {}
        # Exposure cap defaults (will be overridden by ExecutionEngine)
        self.global_cap: Decimal = Decimal("0.50")      # max 50 percent portfolio
        self.symbol_cap: Decimal = Decimal("0.25")      # max 25 percent per symbol
        self.target_vol: Decimal = Decimal("0.20")  # default target vol
        # ------------------------------------------------------------
        # Phase 6.F — Safety Thresholds / Kill-Switch
        # ------------------------------------------------------------
        # If symbol volatility exceeds this → size = 0
        self.vol_kill: Decimal = Decimal("0.15")

        # If portfolio volatility exceeds this → size = 0
        self.portfolio_vol_kill: Decimal = Decimal("0.20")

        # Shock multiplier (vol > shock_mult × avg_vol)
        self.shock_mult: Decimal = Decimal("4")

        # Sliding buffer for shock detection
        self._recent_vols = []

    def apply(
        self,
        symbol: str,
        signal: Optional[str],
        prices: list[Decimal],
        positions: Dict[str, Decimal],
    ) -> Dict[str, Any]:
        """
        Compute intermediate risk adjustments.
        Returns a dict and not a size yet. ExecutionEngine decides final size.
        """
        # -----------------------------------------------
        # 1. Symbol realized volatility estimate
        # -----------------------------------------------
        try:
            vol_est = self.vol_targeter.estimate_vol(symbol, prices)
        except Exception:
            vol_est = Decimal("0")

        # Store vol history (for shock detection)
        try:
            self._recent_vols.append(vol_est)
            if len(self._recent_vols) > 20:
                self._recent_vols = self._recent_vols[-20:]
        except Exception:
            pass

        # -----------------------------------------------
        # 2. Portfolio-level exposure snapshot
        # -----------------------------------------------
        exposure = self.exposure_model.compute_exposure(positions)
        try:
            self.telemetry.last_total_exposure = exposure.get("total_exposure", Decimal("0"))
            self.telemetry.last_symbol_exposure = exposure.get("symbol_exposure", {})
        except Exception:
            pass

        # -----------------------------------------------
        # 3. Portfolio vol estimate (simple weighted proxy)
        # -----------------------------------------------
        try:
            sym_exp = exposure.get("symbol_exposure", {})
            if sym_exp and vol_est > 0:
                portfolio_vol = sum(
                    (Decimal(str(weight)) * vol_est)
                    for weight in sym_exp.values()
                )
            else:
                portfolio_vol = vol_est
        except Exception:
            portfolio_vol = vol_est

        # -----------------------------------------------
        # 4. Volatility targeting scaling factor
        # -----------------------------------------------
        try:
            scaling = self.vol_targeter.scaling_factor(
                portfolio_vol, self.target_vol
            )
        except Exception:
            scaling = Decimal("1")

        # ------------------------------------------------------------
        # Phase 6.F — Kill-Switch Evaluations
        # ------------------------------------------------------------
        panic = False

        # Symbol vol too high
        try:
            if vol_est >= self.vol_kill:
                panic = True
        except Exception:
            pass

        # Portfolio vol too high
        try:
            if portfolio_vol >= self.portfolio_vol_kill:
                panic = True
        except Exception:
            pass

        # Shock rule (vol > shock_mult × mean recent vol)
        try:
            if len(self._recent_vols) >= 5:
                avg_vol = sum(self._recent_vols) / Decimal(len(self._recent_vols))
                if avg_vol > 0 and vol_est > self.shock_mult * avg_vol:
                    panic = True
        except Exception:
            pass

        try:
            self.telemetry.last_panic = panic
        except Exception:
            pass

        # store telemetry
        try:
            self.telemetry.last_vol = vol_est
            self.telemetry.last_portfolio_vol = portfolio_vol
            self.telemetry.last_scaling = scaling
        except Exception:
            pass

        # Build caps passed to sizer (fractions)
        caps = {
            "global_cap": self.global_cap,
            "symbol_cap": self.symbol_cap,
        }

        return {
            "exposure_caps": caps,
            "volatility": vol_est,
            "exposure": exposure,
            "portfolio_vol": portfolio_vol,
            "vol_scaling": scaling,
            "sizer": self.sizer,
            "panic": panic,
        }

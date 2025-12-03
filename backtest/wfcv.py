from __future__ import annotations

from decimal import Decimal
from dataclasses import dataclass
from typing import List, Callable, Any

import pandas as pd

from core.strategy.selector import pick_by_regime
from core.regime_adx import compute_regime_adx
from backtest.metrics import compute_perf, PerformanceMetrics


@dataclass
class WFCVWindowResult:
    start: int
    end: int
    regime: str
    strategy: str
    metrics: PerformanceMetrics


def _simulate_strategy(df: pd.DataFrame, fn: Callable) -> List[Decimal]:
    """
    Tiny simulation: runs strategy over OHLC and returns an equity curve.
    No slippage, volume, or fees at this phase.
    Evaluates signal every bar.
    """
    equity: List[Decimal] = [Decimal("1")]
    position: Decimal = Decimal("0")

    for i in range(1, len(df)):
        sliced = df.iloc[: i + 1]
        try:
            sig = fn(sliced)
        except Exception:
            # fallback to hold
            from core.strategy.types import Signal, Side

            sig = Signal(side=Side.HOLD, strength=Decimal("0"), stop_hint=None, ttl=1)

        # BUY
        try:
            side_val = getattr(sig.side, "value", "HOLD").lower()
        except Exception:
            side_val = str(getattr(sig, "side", "HOLD")).lower()

        if side_val == "buy":
            position = Decimal("1")
        elif side_val == "sell":
            position = Decimal("-1")

        prev_close = Decimal(str(df["close"].iloc[i - 1]))
        cur_close = Decimal(str(df["close"].iloc[i]))

        ret = position * (cur_close / prev_close - Decimal("1")) if prev_close != 0 else Decimal("0")

        equity.append(equity[-1] * (Decimal("1") + ret))

    return equity


def run_wfcv(
    df: pd.DataFrame,
    window: int = 500,
    step: int = 200,
) -> List[WFCVWindowResult]:
    """
    Walk-forward cross-validation:
        - Split OHLC into overlapping windows
        - Classify each window's regime via ADX
        - Route to strategy via StrategySelector
        - Simulate equity curve
        - Compute risk-adjusted metrics
    """
    results: List[WFCVWindowResult] = []

    if len(df) < window:
        return results

    for start in range(0, len(df) - window + 1, step):
        end = start + window
        chunk = df.iloc[start:end]

        regime_obj = compute_regime_adx(chunk)
        regime = regime_obj.label

        strat_name, strat_fn = pick_by_regime(regime)

        equity = _simulate_strategy(chunk, strat_fn)
        perf = compute_perf(equity)

        results.append(
            WFCVWindowResult(
                start=start,
                end=end,
                regime=str(regime),
                strategy=str(strat_name),
                metrics=perf,
            )
        )

    return results


class WalkForwardCV:
    """Walk-forward CV harness that can run engine-backed backtests.

    Accepts an `engine_builder` callable that returns a fresh engine per fold.
    The harness can be toggled to enable Risk Engine v2 via the
    `risk_v2_enabled` attribute.
    """

    def __init__(
        self,
        engine_builder: Callable[[], Any],
        splitter: Any,
        metrics_fn: Callable[[list[Decimal]], PerformanceMetrics],
    ):
        self.engine_builder = engine_builder
        self.splitter = splitter
        self.metrics_fn = metrics_fn
        self.risk_v2_enabled: bool = False

    def run(self, ohlcv: pd.DataFrame) -> List[dict]:
        results: List[dict] = []

        for train_idx, test_idx in self.splitter.split(ohlcv):
            train_data = ohlcv[train_idx[0] : train_idx[1]]
            test_data = ohlcv[test_idx[0] : test_idx[1]]

            regime_obj = compute_regime_adx(train_data)
            regime = regime_obj.label

            # Build engine and enable Risk v2 if requested
            engine = self.engine_builder()
            engine.risk_v2_enabled = self.risk_v2_enabled

            # reset stateful risk variables between folds
            try:
                engine.max_equity_seen = Decimal("0")
                engine.current_drawdown = Decimal("0")
                engine._loss_streak = 0
                engine._prior_equity = Decimal("0")
                engine.risk_off = False
                engine.global_risk_off = False
            except Exception:
                pass

            # training logic (if any strategy calibration required)
            _ = train_data

            # Backtest on test set
            equity = Decimal("10000")
            equity_curve: List[Decimal] = [equity]
            for i in range(len(test_data)):
                row = test_data.iloc[i]
                try:
                    # Convert head slice to list-of-lists expected by engine
                    head = test_data.iloc[: i + 1]
                    ohlcv_rows = [r.tolist() for _, r in head.iterrows()]
                    qty = engine._compute_position_size(
                        None,
                        ohlcv_rows,
                        equity,
                    )
                except Exception:
                    qty = Decimal("0")

                try:
                    prev_close = (
                        Decimal(str(test_data.iloc[i - 1]["close"]))
                        if i > 0
                        else Decimal(str(test_data.iloc[i]["close"]))
                    )
                    cur_close = Decimal(str(row["close"]))
                    pnl = qty * (cur_close - prev_close)
                    equity = equity + pnl
                except Exception:
                    pass

                equity_curve.append(equity)

            result = self.metrics_fn(equity_curve)
            # inject risk metrics for research use
            out = {
                "start": int(test_idx[0]),
                "end": int(test_idx[1]),
                "regime": str(regime),
                "metrics": result,
                "max_drawdown": float(getattr(engine, "current_drawdown", Decimal("0"))),
                "loss_streak": int(getattr(engine, "_loss_streak", 0)),
                "risk_off": bool(getattr(engine, "risk_off", False) or getattr(engine, "global_risk_off", False)),
            }
            results.append(out)

        return results

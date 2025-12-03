from __future__ import annotations

import pandas as pd
from decimal import Decimal
from typing import Callable, Any

from backtest.wfcv import run_wfcv


class BacktestRunner:
    """Simple backtest runner that can toggle Risk Engine v2 for experiments.

    This is intentionally minimal: it accepts an engine_builder callable that
    returns a fresh `ExecutionEngine`-like object and runs a single-pass
    backtest over provided OHLCV rows calling the engine's
    `_compute_position_size` to obtain Decimal qtys.
    """

    def __init__(self, engine_builder: Callable[[], Any], ohlcv: list[list[Any]], initial_equity: Decimal):
        self.engine_builder = engine_builder
        self.ohlcv = ohlcv
        self.initial_equity = initial_equity
        self.risk_v2_enabled: bool = False

    def run(self) -> list[Decimal]:
        engine = self.engine_builder()

        # Risk Engine v2 toggle for backtests
        engine.risk_v2_enabled = self.risk_v2_enabled

        equity = self.initial_equity
        equity_curve: list[Decimal] = [equity]

        for i in range(len(self.ohlcv)):
            row = self.ohlcv[i]
            try:
                qty = engine._compute_position_size(
                    signal=None,
                    ohlcv=self.ohlcv[: i + 1],
                    equity=equity,
                )
            except Exception:
                qty = Decimal("0")

            # simple pnl: qty * (cur_close - prev_close)
            try:
                prev_close = Decimal(str(self.ohlcv[i - 1][4])) if i > 0 else Decimal(str(self.ohlcv[i][4]))
                cur_close = Decimal(str(row[4]))
                pnl = qty * (cur_close - prev_close)
                equity = equity + pnl
            except Exception:
                # if price access fails, keep equity unchanged
                pass

            equity_curve.append(equity)

        return equity_curve


def run(path: str):
    df = pd.read_csv(path)
    # accept common timestamp column names
    # normalize to expected names if present
    if "timestamp" in df.columns and "open" in df.columns:
        df = df[["timestamp", "open", "high", "low", "close", "volume"]]

    results = run_wfcv(df)
    for r in results:
        print(r)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: runner.py path/to/ohlc.csv")
    else:
        run(sys.argv[1])

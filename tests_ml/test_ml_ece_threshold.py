import json
from pathlib import Path
from ml.train_intent_veto import train_intent_veto
import pandas as pd
import numpy as np


def test_ece_below_three_percent(tmp_path: Path):
    # minimal synthetic dataset to verify calibration target
    n = 300
    ts = np.arange(n)
    price = 100 + np.cumsum(np.random.normal(0, 0.5, n))
    candles = pd.DataFrame(
        {
            "ts": ts,
            "open": price,
            "high": price * 1.001,
            "low": price * 0.999,
            "close": price,
            "symbol": "BTCUSDT",
        }
    )
    # random but slightly imbalanced signals
    signals = pd.DataFrame(
        {
            "ts": ts[::6],
            "symbol": "BTCUSDT",
            "side": np.random.choice([1, -1], size=len(ts[::6])),
        }
    )

    candles_csv = tmp_path / "candles.csv"
    signals_csv = tmp_path / "signals.csv"
    candles.to_csv(candles_csv, index=False)
    signals.to_csv(signals_csv, index=False)

    outdir = tmp_path / "models" / "intent_veto"
    res = train_intent_veto(signals_csv, candles_csv, outdir, horizon=8)
    meta = json.loads(Path(res["meta_path"]).read_text())
    ece = meta["validation"]["ece"]
    assert ece < 0.03, f"ECE too high: {ece}"

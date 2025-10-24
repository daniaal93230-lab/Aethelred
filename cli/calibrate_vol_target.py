import argparse
import yaml  # type: ignore[import-untyped]
import pandas as pd
import numpy as np
from sizing.vol_target import VolConfig, calibrate_global_k


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--features", default="exports/features.parquet")
    p.add_argument("--trades", default="exports/trades.csv")
    p.add_argument("--config", default="config/risk.yaml")
    p.add_argument("--out-config", default="config/risk.yaml")
    args = p.parse_args()

    with open(args.config, "r") as f:
        cfg = yaml.safe_load(f)
    vcfg = VolConfig(
        target_annualized=cfg["vol_target"]["target_annualized"],
        lookback_bars=cfg["vol_target"]["lookback_bars"],
        ewma_lambda=cfg["vol_target"]["ewma_lambda"],
        atr_n=cfg["vol_target"]["atr_n"],
    )
    trades = pd.read_csv(args.trades, parse_dates=["ts"])

    def daily_vol_for_k(k: float) -> float:
        # Placeholder: reconstruct daily returns scaled by k (user should replace with replay)
        daily = trades.groupby(trades["ts"].dt.date)["pnl_pct"].sum() * k
        return float(daily.std() * np.sqrt(252))

    k = calibrate_global_k(
        daily_vol_for_k, bracket=tuple(cfg["vol_target"]["k_initial_bracket"]), target=vcfg.target_annualized
    )
    cfg["vol_target_k"] = float(k)
    with open(args.out_config, "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)
    print(f"Calibrated k={k:.4f} saved to {args.out_config}")


if __name__ == "__main__":
    main()

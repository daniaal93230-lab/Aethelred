from __future__ import annotations

import argparse
import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Tuple

import numpy as np
import pandas as pd


LOGGER = logging.getLogger(__name__)


@dataclass
class TrainConfig:
    """Configuration for training the Meta Signal Ranker."""

    input_path: Path
    output_path: Path
    meta_path: Path
    target_column: str = "target"
    test_fraction: float = 0.2
    random_state: int = 42
    n_estimators: int = 200
    max_depth: int = 4
    learning_rate: float = 0.05
    subsample: float = 0.8
    colsample_bytree: float = 0.8


def build_dataset(
    df: pd.DataFrame,
    target_column: str = "target",
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """
    Build a feature matrix and target vector from a raw dataframe.

    The dataset is expected to already contain synthetic features such as:
    - signal strength
    - one hot regimes
    - volatility metrics
    - donchian width
    - moving average slopes
    - RSI values
    - intent veto features

    The only requirement for this helper is that the label column is named
    via `target_column`.
    """
    if target_column not in df.columns:
        raise ValueError(f"Missing target column '{target_column}' in dataset")

    df_clean = df.dropna(subset=[target_column]).copy()

    feature_columns = [c for c in df_clean.columns if c != target_column]
    if not feature_columns:
        raise ValueError("No feature columns found for training")

    x_mat = df_clean[feature_columns].to_numpy(dtype=np.float32)
    y_vec = df_clean[target_column].to_numpy(dtype=np.float32)

    return x_mat, y_vec, feature_columns


def compute_checksum(path: Path) -> str:
    """Compute a hex encoded sha256 checksum for a file."""
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def write_meta(meta_path: Path, payload: dict[str, Any]) -> None:
    """Write a small JSON metadata sidecar file."""
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def _load_input_frame(input_path: Path) -> pd.DataFrame:
    """Load input data from a parquet or csv file."""
    if not input_path.exists():
        raise FileNotFoundError(str(input_path))

    suffix = input_path.suffix.lower()
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(input_path)
    if suffix in {".csv"}:
        return pd.read_csv(input_path)

    raise ValueError(f"Unsupported dataset extension: {suffix}")


def train_signal_ranker(config: TrainConfig) -> dict[str, Any]:
    """
    Train an XGBoost based signal ranker on a prebuilt feature dataset.

    This function deliberately keeps the XGBoost import behind importlib
    so that importing this module does not require xgboost to be installed.
    """
    import importlib

    LOGGER.info("Loading dataset from %s", config.input_path)
    df = _load_input_frame(config.input_path)

    x_mat, y_vec, feature_columns = build_dataset(df, target_column=config.target_column)

    if x_mat.shape[0] < 10:
        raise ValueError("Dataset too small for training (need at least 10 rows)")

    n_rows = x_mat.shape[0]
    split_idx = int(n_rows * (1.0 - config.test_fraction))
    if split_idx <= 0 or split_idx >= n_rows:
        raise ValueError("Invalid test_fraction; resulted in empty train or test split")

    x_train = x_mat[:split_idx]
    y_train = y_vec[:split_idx]
    x_valid = x_mat[split_idx:]
    y_valid = y_vec[split_idx:]

    LOGGER.info(
        "Training signal ranker on %s rows (%s train / %s valid, %s features)",
        n_rows,
        x_train.shape[0],
        x_valid.shape[0],
        x_mat.shape[1],
    )

    xgb_module = importlib.import_module("xgboost")
    XGBRegressor = getattr(xgb_module, "XGBRegressor")

    model = XGBRegressor(
        objective="reg:squarederror",
        n_estimators=config.n_estimators,
        max_depth=config.max_depth,
        learning_rate=config.learning_rate,
        subsample=config.subsample,
        colsample_bytree=config.colsample_bytree,
        tree_method="hist",
        random_state=config.random_state,
    )

    model.fit(x_train, y_train, eval_set=[(x_valid, y_valid)], verbose=False)

    # Persist the model as a JSON file in the models directory.
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    booster = model.get_booster()
    booster.save_model(str(config.output_path))

    checksum = compute_checksum(config.output_path)

    # Evaluate a simple RMSE on the validation slice for quick sanity checks.
    y_pred_valid = model.predict(x_valid)
    mse = float(np.mean((y_pred_valid - y_valid) ** 2))
    rmse = float(np.sqrt(mse))

    meta: dict[str, Any] = {
        "version": "v1-signal-ranker",
        "checksum": checksum,
        "n_rows": int(n_rows),
        "n_features": int(x_mat.shape[1]),
        "features": feature_columns,
        "metrics": {
            "rmse_valid": rmse,
        },
        "target_column": config.target_column,
    }

    write_meta(config.meta_path, meta)
    LOGGER.info("Saved signal ranker to %s (checksum %s)", config.output_path, checksum)

    return meta


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train the Meta Signal Ranker model.")
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to input dataset (parquet or csv) with features and target.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("models") / "signal_ranker.json",
        help="Output path for the trained model JSON.",
    )
    parser.add_argument(
        "--meta-output",
        type=Path,
        default=Path("models") / "signal_ranker.meta.json",
        help="Output path for the metadata sidecar file.",
    )
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = _build_arg_parser()
    args = parser.parse_args()

    config = TrainConfig(
        input_path=args.input,
        output_path=args.output,
        meta_path=args.meta_output,
    )

    train_signal_ranker(config)


if __name__ == "__main__":
    main()

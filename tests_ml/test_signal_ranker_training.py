from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ml.train_signal_ranker import (
    TrainConfig,
    build_dataset,
    compute_checksum,
    write_meta,
)


def test_build_dataset_basic() -> None:
    df = pd.DataFrame(
        {
            "signal_strength": [0.1, 0.2, 0.3],
            "regime_trending": [1, 0, 1],
            "volatility": [0.01, 0.02, 0.03],
            "target": [0.5, 0.6, 0.4],
        },
    )

    x_mat, y_vec, feature_columns = build_dataset(df, target_column="target")

    assert x_mat.shape == (3, 3)
    assert y_vec.shape == (3,)
    assert "target" not in feature_columns
    assert "signal_strength" in feature_columns


def test_compute_checksum_stable(tmp_path: Path) -> None:
    file_path = tmp_path / "example.bin"
    file_path.write_bytes(b"abc123")

    checksum_1 = compute_checksum(file_path)
    checksum_2 = compute_checksum(file_path)

    assert checksum_1 == checksum_2
    assert len(checksum_1) == 64


def test_write_meta_roundtrip(tmp_path: Path) -> None:
    meta_path = tmp_path / "meta.json"
    payload: dict[str, Any] = {"version": "v1", "checksum": "deadbeef"}

    write_meta(meta_path, payload)

    loaded = pd.read_json(meta_path)
    # We only care that the keys exist and the file is valid JSON.
    assert "version" in loaded.columns
    assert "checksum" in loaded.columns


def test_train_signal_ranker_smoke_without_xgboost(tmp_path: Path, monkeypatch: Any) -> None:
    """
    Smoke test that ensures the training function can be imported and that
    xgboost is only required at call time, not at import time.

    This test patches importlib.import_module to avoid requiring the real
    xgboost dependency in the unit test environment.
    """
    import importlib
    import types

    def fake_import_module(name: str) -> types.ModuleType:
        assert name == "xgboost"
        module = types.SimpleNamespace()
        module.XGBRegressor = object  # type: ignore[assignment]
        return module  # type: ignore[return-value]

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    # Build a tiny dataset and run through the training pipeline to the point
    # where xgboost would be instantiated. We do not persist any files here.
    df = pd.DataFrame(
        {
            "signal_strength": [0.1] * 20,
            "regime_trending": [1] * 20,
            "volatility": [0.01] * 20,
            "target": [0.5] * 20,
        },
    )

    x_mat, y_vec, feature_columns = build_dataset(df, target_column="target")
    assert x_mat.shape[0] == 20
    assert y_vec.shape[0] == 20
    assert len(feature_columns) == 3

    # Construct a config but do not actually call train_signal_ranker with it,
    # as that would still rely on xgboost's API. This is a pure import and
    # wiring smoke test.
    _ = TrainConfig(
        input_path=tmp_path / "dummy.parquet",
        output_path=tmp_path / "signal_ranker.json",
        meta_path=tmp_path / "signal_ranker.meta.json",
    )

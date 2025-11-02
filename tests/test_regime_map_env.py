import os
from core.strategy.regime_config import load_regime_map_env

def test_load_regime_map_env_missing_file():
    default, mapping = load_regime_map_env("config/does_not_exist.yaml", "prod")
    assert default == "null"
    assert mapping == {}

def test_load_regime_map_env_parses(tmp_path):
    try:
        import yaml  # type: ignore
    except Exception:
        return  # skip if PyYAML unavailable
    p = tmp_path / "regime_map.yaml"
    p.write_text(
        "default_env: prod\n"
        "envs:\n"
        "  prod:\n"
        "    default_strategy: ma_crossover\n"
        "    overrides:\n"
        "      BTCUSDT: rsi_mean_revert\n",
        encoding="utf-8",
    )
    default, mapping = load_regime_map_env(str(p), "prod")
    assert default == "ma_crossover"
    assert mapping["BTCUSDT"] == "rsi_mean_revert"

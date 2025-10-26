from core.strategy.regime_config import load_regime_map
import io, os, tempfile, textwrap

def test_load_regime_map_handles_missing_file():
    default, mapping = load_regime_map("config/does_not_exist.yaml")
    assert default == "unknown"
    assert mapping == {}

def test_load_regime_map_parses_yaml_when_available(tmp_path):
    try:
        import yaml  # type: ignore
    except Exception:
        # If PyYAML is not installed in this env, skip this test
        return
    p = tmp_path / "selector.yaml"
    p.write_text(textwrap.dedent("""
    defaults:
      regime: trending
    overrides:
      BTCUSDT: trending
      ETHUSDT: mean_revert
    """), encoding="utf-8")
    default, mapping = load_regime_map(str(p))
    assert default == "trending"
    assert mapping["BTCUSDT"] == "trending"
    assert mapping["ETHUSDT"] == "mean_revert"

from core.strategy import registry


def test_default_registry_contains_core_entries() -> None:
    reg = registry.default_registry()
    assert isinstance(reg, dict)
    # minimal expectations: null and ma_crossover should exist
    assert "null" in reg
    assert "ma_crossover" in reg
    # values should expose a readable name attribute
    for k, v in reg.items():
        assert hasattr(v, "name")
        assert isinstance(v.name, str)

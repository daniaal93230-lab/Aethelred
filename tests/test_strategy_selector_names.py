from core.strategy.selector import StrategySelector
from core.strategy.base import NullStrategy

def test_selector_strategy_name_fallback():
    sel = StrategySelector()
    s = NullStrategy()
    name = sel.strategy_name(s)
    assert isinstance(name, str)
    assert len(name) > 0

from typing import Any, Dict

import pytest

from core.strategy.selector import StrategySelector
from core.strategy.base import Strategy, NullStrategy


class DummyStrategy(Strategy):
    name = "dummy"

    def __init__(self) -> None:
        self.prepared_with: Dict[str, Any] | None = None

    def prepare(self, ctx: Dict[str, Any]) -> None:
        # record the context so tests can assert prepare_for invoked prepare
        self.prepared_with = dict(ctx or {})

    def generate_signal(self, market_state: Dict[str, Any]):
        raise NotImplementedError()


def test_pick_known_and_unknown_regime() -> None:
    s = StrategySelector()
    # trending maps to ma_crossover by default
    strat = s.pick("BTCUSDT", "trending")
    assert hasattr(strat, "name")
    assert isinstance(strat.name, str)

    # unknown regime should fall back to DonchianBreakout (name present)
    fallback = s.pick("BTCUSDT", "this_does_not_exist")
    assert hasattr(fallback, "name")


def test_register_override_is_case_insensitive() -> None:
    s = StrategySelector()
    # register an override for lowercase symbol
    s.register_override("btcusdt", "trending", NullStrategy(ttl=5))
    # pick using uppercase symbol should return the override
    chosen = s.pick("BTCUSDT", "trending")
    assert chosen.name == "null"


def test_prepare_for_calls_prepare() -> None:
    s = StrategySelector()
    dummy = DummyStrategy()
    # replace the trending regime with our dummy
    s.register_regime("trending", dummy)
    ctx = {"foo": "bar"}
    returned = s.prepare_for("BTCUSDT", "trending", ctx)
    assert returned is dummy
    assert dummy.prepared_with == ctx


def test_register_name_and_pick_by_name_and_fallback() -> None:
    s = StrategySelector()
    dummy = DummyStrategy()
    s.register_name("my_dummy", dummy)
    assert s.pick_by_name("my_dummy") is dummy
    # None or unknown names return the fallback strategy
    assert hasattr(s.pick_by_name(None), "name")
    assert hasattr(s.pick_by_name("unknown_name"), "name")

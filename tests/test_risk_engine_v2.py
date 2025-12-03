from decimal import Decimal

from core.execution_engine import ExecutionEngine


class MockExchange:
    """
    Minimal mock to simulate exposure and equity for risk tests.
    """

    def __init__(self, exposure: Decimal = Decimal("0")):
        self._exposure = exposure

    def account_overview(self):
        return {
            "total_exposure": str(self._exposure)
        }


def build_engine():
    """
    Factory for a standalone ExecutionEngine instance.
    Only dependencies actually used in Risk Engine V2 are mocked.
    """
    eng = ExecutionEngine()
    eng.exchange = MockExchange()
    eng.symbol = "TEST"
    eng.risk_v2_enabled = True
    return eng


def synthetic_ohlcv(n=30, base=100):
    """
    Generate synthetic OHLCV with increasing close prices.
    Returns list-of-lists: [ts, open, high, low, close, vol]
    """
    data = []
    for i in range(n):
        price = float(base + i)
        data.append([
            0,          # timestamp
            price,      # open
            price,      # high
            price,      # low
            price,      # close
            1,          # volume
        ])
    return data


def test_global_risk_off_overrides_all():
    eng = build_engine()
    eng.global_risk_off = True
    ohlcv = synthetic_ohlcv()
    price = float(ohlcv[-1][4])
    qty = eng._compute_position_size(None, ohlcv, Decimal("10000"), price)
    assert qty == Decimal("0")


def test_hard_drawdown_has_priority_over_all_below():
    eng = build_engine()
    eng.hard_dd_threshold = Decimal("0.20")
    eng.max_equity_seen = Decimal("10000")

    # 25 percent DD triggers kill-switch
    dd_equity = Decimal("7500")
    ohlcv = synthetic_ohlcv()
    price = float(ohlcv[-1][4])

    qty = eng._compute_position_size(None, ohlcv, dd_equity, price)
    assert qty == Decimal("0"), "Hard DD should force zero quantity"


def test_loss_streak_kill_switch():
    eng = build_engine()
    eng.max_consecutive_losses = 3
    eng._loss_streak = 3

    ohlcv = synthetic_ohlcv()
    price = float(ohlcv[-1][4])
    qty = eng._compute_position_size(None, ohlcv, Decimal("10000"), price)
    assert qty == Decimal("0"), "Loss streak should force zero quantity"


def test_exposure_cap_applied():
    eng = build_engine()
    eng.per_symbol_exposure_limit = Decimal("0.10")   # 10 percent
    eng.global_portfolio_limit = Decimal("0.20")      # 20 percent

    eng.exchange = MockExchange(exposure=Decimal("1500"))  # existing exposure

    ohlcv = synthetic_ohlcv()
    equity = Decimal("10000")
    price = float(ohlcv[-1][4])

    qty = eng._compute_position_size(None, ohlcv, equity, price)

    # demand should not exceed per-symbol 10 percent = 1000 notional
    # and global headroom = 2000 - 1500 = 500 notional
    # so expected qty = 500 / latest price
    last_price = Decimal(str(ohlcv[-1][4]))
    assert qty <= (Decimal("500") / last_price)


def test_vol_target_sizing_nonzero_when_safe():
    eng = build_engine()
    ohlcv = synthetic_ohlcv()
    price = float(ohlcv[-1][4])

    # normal safe scenario
    qty = eng._compute_position_size(None, ohlcv, Decimal("10000"), price)

    assert qty > 0, "Vol targeting should produce a positive qty under safe conditions"

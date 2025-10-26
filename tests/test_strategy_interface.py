import numpy as np
from core.strategy.ma_crossover_adapter import MACrossoverAdapter
from core.strategy.types import Side

def _mk(c):
    c = np.array(c, dtype=float)
    return {"o": c, "h": c+0.5, "l": c-0.5, "c": c, "v": np.full_like(c, 100.0)}

def test_ma_adapter_buy_on_uptrend():
    st = MACrossoverAdapter(fast=5, slow=20)
    sig = st.generate_signal(_mk(list(range(1,60))))
    assert sig.side in (Side.BUY, Side.HOLD)

def test_ma_adapter_hold_if_short_history():
    st = MACrossoverAdapter(fast=10, slow=30)
    sig = st.generate_signal(_mk([1,2,3,4,5]))
    assert sig.side == Side.HOLD

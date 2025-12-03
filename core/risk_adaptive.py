from __future__ import annotations

from decimal import Decimal, getcontext
from typing import Iterable, List

getcontext().prec = 50


def _to_decimal_list(values: Iterable[float | Decimal]) -> List[Decimal]:
    return [v if isinstance(v, Decimal) else Decimal(str(v)) for v in values]


def compute_atr(high: Iterable[float | Decimal],
                low: Iterable[float | Decimal],
                close: Iterable[float | Decimal],
                period: int = 14) -> Decimal:
    """
    Wilder ATR with Decimal precision.
    Returns the latest ATR value (not a series).
    """
    highs = _to_decimal_list(high)
    lows = _to_decimal_list(low)
    closes = _to_decimal_list(close)

    if len(highs) < period + 1:
        return Decimal("0")

    trs: List[Decimal] = []
    for i in range(1, len(highs)):
        tr1 = highs[i] - lows[i]
        tr2 = abs(highs[i] - closes[i - 1])
        tr3 = abs(lows[i] - closes[i - 1])
        trs.append(max(tr1, tr2, tr3))

    # Wilder's smoothing: start with first TR as initial ATR
    atr = trs[0]
    # Use min(period, len(trs)) to avoid index errors
    n = min(period, len(trs))
    for i in range(1, n):
        atr = (atr * Decimal(n - 1) + trs[i]) / Decimal(n)

    return atr


def compute_return_vol(close: Iterable[float | Decimal], period: int = 20) -> Decimal:
    """
    Standard deviation of log returns with Decimal math.
    Returns the latest rolling stdev over `period` or 0 when insufficient data.
    """
    closes = _to_decimal_list(close)

    if len(closes) < period + 1:
        return Decimal("0")

    rets: List[Decimal] = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            # Decimal has no natural log; approximate via float safely for log then convert back
            # Use math.log on float for performance and convert to Decimal
            import math

            r = Decimal(str(math.log(float(closes[i] / closes[i - 1]))))
            rets.append(r)

    if len(rets) < 2:
        return Decimal("0")

    window = rets[-period:]
    mean_r = sum(window) / Decimal(len(window))
    var = sum((r - mean_r) ** 2 for r in window) / Decimal(len(window))

    # sqrt via Decimal's sqrt on quantized value
    try:
        return var.sqrt()
    except Exception:
        # fallback to float sqrt
        import math

        return Decimal(str(math.sqrt(float(var))))


def regime_scaler(regime: str) -> Decimal:
    """
    Apply volatility scaling per regime.
    - trend: allow larger sizing
    - chop: reduce sizing
    - transition/unknown: baseline
    """
    r = (regime or "").lower()
    if r == "trend":
        return Decimal("1.40")
    if r == "chop":
        return Decimal("0.65")
    return Decimal("1.00")


def compute_hybrid_vol(atr: Decimal, ret_vol: Decimal, price: Decimal) -> Decimal:
    """
    Hybrid volatility = 0.5 * ATR/price + 0.5 * return_vol.
    """
    if price <= 0:
        return Decimal("0")

    atr_norm = atr / price
    return (atr_norm * Decimal("0.5")) + (ret_vol * Decimal("0.5"))


def target_position_size(equity: Decimal,
                         hybrid_vol: Decimal,
                         regime_scale: Decimal,
                         target_vol: Decimal = Decimal("0.02")) -> Decimal:
    """
    Core vol-target sizing:
    size = (equity * target_vol * scaler) / hybrid_vol

    Returns notional USD position (Decimal). ExecutionEngine converts notional -> qty.
    """
    if hybrid_vol <= 0:
        return Decimal("0")

    return (equity * target_vol * regime_scale) / hybrid_vol


class AdaptiveRiskEngineV2:
    """
    Reusable hybrid vol targeting engine.
    Stateless; `compute()` called each cycle with recent OHLCV arrays.
    """
    def compute(self,
                high: Iterable[float | Decimal],
                low: Iterable[float | Decimal],
                close: Iterable[float | Decimal],
                regime: str,
                equity: Decimal,
                price: Decimal) -> Decimal:

        highs = _to_decimal_list(high)
        lows = _to_decimal_list(low)
        closes = _to_decimal_list(close)

        atr = compute_atr(highs, lows, closes)
        ret_vol = compute_return_vol(closes)
        scaler = regime_scaler(regime)
        hybrid_vol = compute_hybrid_vol(atr, ret_vol, price)

        notional = target_position_size(
            equity=equity,
            hybrid_vol=hybrid_vol,
            regime_scale=scaler,
        )
        return notional

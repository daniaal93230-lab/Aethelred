from decimal import Decimal
from typing import Dict


def decimal_or_zero(v) -> Decimal:
    """Safe decimal conversion for metrics."""
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal("0")


def compute_mae_mfe(entry_price: Decimal, high: Decimal, low: Decimal) -> Dict[str, Decimal]:
    """
    Compute per-trade MAE and MFE.
    MAE = max adverse excursion (how far price went against the trade)
    MFE = max favorable excursion (how far price moved in favor)

    Returns fractions relative to entry_price (0..inf), Decimal-safe.
    """
    try:
        mae = (entry_price - low) / entry_price if entry_price and entry_price > 0 else Decimal("0")
    except Exception:
        mae = Decimal("0")

    try:
        mfe = (high - entry_price) / entry_price if entry_price and entry_price > 0 else Decimal("0")
    except Exception:
        mfe = Decimal("0")

    return {"mae": mae, "mfe": mfe}

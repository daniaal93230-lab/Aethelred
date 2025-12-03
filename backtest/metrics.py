from __future__ import annotations

from decimal import Decimal, getcontext
from dataclasses import dataclass
from typing import Sequence

getcontext().prec = 28


@dataclass
class PerformanceMetrics:
    sharpe: Decimal
    sortino: Decimal
    calmar: Decimal
    total_return: Decimal
    max_drawdown: Decimal


def _dec(x) -> Decimal:
    try:
        return Decimal(str(x))
    except Exception:
        return Decimal("0")


def compute_drawdown(equity: Sequence[Decimal]) -> Decimal:
    if not equity:
        return Decimal("0")
    peak = equity[0]
    max_dd = Decimal("0")
    for e in equity:
        if e > peak:
            peak = e
        dd = (peak - e) / peak if peak != 0 else Decimal("0")
        if dd > max_dd:
            max_dd = dd
    return max_dd


def compute_sharpe(returns: Sequence[Decimal]) -> Decimal:
    if len(returns) < 2:
        return Decimal("0")
    mean = sum(returns) / Decimal(len(returns))
    var = sum((r - mean) ** 2 for r in returns) / Decimal(len(returns) - 1)
    try:
        std = var.sqrt()
    except Exception:
        std = Decimal("0")
    return mean / std if std != 0 else Decimal("0")


def compute_sortino(returns: Sequence[Decimal]) -> Decimal:
    neg = [r for r in returns if r < 0]
    if not neg:
        return Decimal("0")
    mean = sum(returns) / Decimal(len(returns))
    var = sum((r - Decimal("0")) ** 2 for r in neg) / Decimal(len(neg))
    try:
        std = var.sqrt()
    except Exception:
        std = Decimal("0")
    return mean / std if std != 0 else Decimal("0")


def compute_perf(equity: Sequence[Decimal]) -> PerformanceMetrics:
    if len(equity) < 2:
        return PerformanceMetrics(
            sharpe=Decimal("0"),
            sortino=Decimal("0"),
            calmar=Decimal("0"),
            total_return=Decimal("0"),
            max_drawdown=Decimal("0"),
        )

    returns = []
    for i in range(1, len(equity)):
        prev = equity[i - 1]
        cur = equity[i]
        if prev == 0:
            returns.append(Decimal("0"))
        else:
            returns.append((cur - prev) / prev)

    max_dd = compute_drawdown(equity)
    calmar = (equity[-1] / equity[0] - Decimal("1")) / max_dd if max_dd != 0 else Decimal("0")

    return PerformanceMetrics(
        sharpe=compute_sharpe(returns),
        sortino=compute_sortino(returns),
        calmar=calmar,
        total_return=(equity[-1] / equity[0] - Decimal("1")),
        max_drawdown=max_dd,
    )

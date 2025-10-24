from typing import Dict, Any
from core.risk import RiskEngine


def acct(
    equity: float, total_notional: float = 0.0, sym_notional: float = 0.0, dd_today_pct: float = 0.0
) -> Dict[str, Any]:
    return {
        "equity_now": equity,
        "total_notional": total_notional,
        "positions_by_symbol": {"BTC/USDT": {"notional": sym_notional}},
        "drawdown_pct_today": dd_today_pct,
    }


def test_portfolio_exposure_limit():
    cfg = {
        "exposure": {"set_as_fraction": True, "max_exposure_usd": 0.35, "per_symbol_exposure_pct": 0.20},
        "max_leverage": 10,
    }
    risk = RiskEngine(cfg)
    a = acct(10_000.0, total_notional=3_400.0)
    order = {"symbol": "BTC/USDT", "side": "buy", "qty": 0.02, "mid_price": 10_000.0}
    dec = risk.check(a, {**order, "notional": order["qty"] * order["mid_price"]})
    assert dec.allow is False
    assert "portfolio_exposure" in dec.reason


def test_per_symbol_exposure_limit():
    cfg = {
        "exposure": {"set_as_fraction": True, "max_exposure_usd": 0.50, "per_symbol_exposure_pct": 0.20},
        "max_leverage": 10,
    }
    risk = RiskEngine(cfg)
    a = acct(10_000.0, total_notional=1_900.0, sym_notional=1_950.0)
    order = {"symbol": "BTC/USDT", "side": "buy", "qty": 0.01, "mid_price": 10_000.0}
    dec = risk.check(a, {**order, "notional": 100.0})
    assert dec.allow is False
    assert "per_symbol_exposure" in dec.reason


def test_leverage_limit():
    cfg = {
        "exposure": {"set_as_fraction": False, "max_exposure_usd": 1e12, "per_symbol_exposure_pct": 1.0},
        "max_leverage": 1.5,
    }
    risk = RiskEngine(cfg)
    a = acct(10_000.0, total_notional=14_900.0)
    order = {"symbol": "BTC/USDT", "side": "buy", "qty": 0.11, "mid_price": 10_000.0}
    dec = risk.check(a, {**order, "notional": 1_100.0})
    assert dec.allow is False
    assert "leverage" in dec.reason


def test_daily_loss_breaker():
    cfg = {
        "daily_loss_limit_pct": 3.0,
        "exposure": {"set_as_fraction": True, "max_exposure_usd": 0.35, "per_symbol_exposure_pct": 0.20},
        "max_leverage": 10,
    }
    risk = RiskEngine(cfg)
    a = acct(10_000.0, dd_today_pct=-3.2)
    order = {"symbol": "BTC/USDT", "side": "buy", "qty": 0.01, "mid_price": 10_000.0, "notional": 100.0}
    dec = risk.check(a, order)
    assert dec.allow is False
    assert "breaker:daily_loss" in dec.reason


def test_per_trade_risk_limit():
    cfg = {
        "per_trade_risk_pct": 0.5,
        "exposure": {"set_as_fraction": True, "max_exposure_usd": 1.0, "per_symbol_exposure_pct": 1.0},
        "max_leverage": 10,
    }
    risk = RiskEngine(cfg)
    a = acct(10_000.0)
    # buy at 100, stop 99, qty 60 -> est_loss 60 > 50 budget
    order = {
        "symbol": "BTC/USDT",
        "side": "buy",
        "qty": 60.0,
        "mid_price": 100.0,
        "notional": 6_000.0,
        "est_stop_price": 99.0,
    }
    dec = risk.check(a, order)
    assert dec.allow is False
    assert "per_trade_risk" in dec.reason

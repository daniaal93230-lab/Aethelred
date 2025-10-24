from typing import Dict, Any, Tuple, Callable, Optional


def _mid_price(exchange: Any, symbol: str) -> float:
    if hasattr(exchange, "mid_price"):
        try:
            mp = exchange.mid_price(symbol)
            if mp and mp > 0:
                return float(mp)
        except Exception:
            pass
    if hasattr(exchange, "get_quote"):
        try:
            q = exchange.get_quote(symbol)
            if isinstance(q, dict):
                bid = float(q.get("bid") or 0)
                ask = float(q.get("ask") or 0)
                if bid > 0 and ask > 0:
                    return (bid + ask) / 2.0
                last = float(q.get("last") or 0)
                if last > 0:
                    return last
        except Exception:
            pass
    if hasattr(exchange, "price"):
        try:
            p = float(exchange.price(symbol))
            if p > 0:
                return p
        except Exception:
            pass
    if hasattr(exchange, "ticker"):
        try:
            t = exchange.ticker(symbol)
            if isinstance(t, dict):
                last = float(t.get("last") or 0)
                if last > 0:
                    return last
        except Exception:
            pass
    raise RuntimeError(f"Cannot resolve mid price for {symbol}")


def enrich_order_for_risk(exchange: Any, order: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(order)
    symbol = out["symbol"]
    qty = float(out["qty"])
    if "mid_price" not in out or not out.get("mid_price"):
        out["mid_price"] = _mid_price(exchange, symbol)
    if "notional" not in out or not out.get("notional"):
        out["notional"] = abs(qty) * float(out["mid_price"])
    return out


def vet_order(
    risk_engine: Any,
    acct: Dict[str, Any],
    exchange: Any,
    order: Dict[str, Any],
) -> Tuple[bool, Dict[str, Any], Dict[str, Any]]:
    enriched = enrich_order_for_risk(exchange, order)
    decision = risk_engine.check(acct, enriched)
    info = {
        "reason": getattr(decision, "reason", "ok" if getattr(decision, "allow", False) else "blocked"),
        "details": getattr(decision, "details", {}) or {},
    }
    return bool(getattr(decision, "allow", False)), info, enriched


def place_if_allowed(
    risk_engine: Any,
    acct: Dict[str, Any],
    exchange: Any,
    order: Dict[str, Any],
    place_func: Callable[[Dict[str, Any]], Any],
    logger: Any = None,
    veto_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
):
    """
    Gate a single order through risk. If allowed, calls place_func(order)
    and returns its result. If blocked, logs and optionally writes to veto_sink(payload).
    """
    allow, info, enriched = vet_order(risk_engine, acct, exchange, order)
    if not allow:
        payload = {
            "symbol": enriched["symbol"],
            "side": enriched["side"],
            "qty": float(enriched["qty"]),
            "notional": float(enriched["notional"]),
            "reason": info["reason"],
            "details": info["details"],
        }
        if logger:
            try:
                logger.info(f"VETO {payload}")
            except Exception:
                pass
        if veto_sink:
            try:
                veto_sink(payload)
            except Exception:
                if logger:
                    try:
                        logger.exception("veto_sink failed")
                    except Exception:
                        pass
        return None
    return place_func(enriched)
    return place_func(enriched)

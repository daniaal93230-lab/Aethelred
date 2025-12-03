try:
    from exchange.paper import PaperExchange
except Exception:
    try:
        # older location (compatibility shim) — prefer canonical `exchange`
        from exchange import PaperExchange
    except Exception:
        PaperExchange = None

from utils.aud import append_audit


def flatten_all_safe(reason: str = "") -> int:
    try:
        ex = PaperExchange()
    except Exception:
        # If exchange ctor needs params, no-op flatten
        append_audit("FLATTEN_FAIL", {"reason": reason})
        return 0
    count = 0
    try:
        positions = ex.positions()
        for p in positions:
            try:
                qty = float(p.get("qty") or p.get("amount") or 0.0)
            except Exception:
                qty = 0.0
            if qty:
                ex.market_close(p["symbol"])  # assume exchange adapter exposes this
                count += 1
    except Exception:
        pass
    append_audit("FLATTEN", {"reason": reason, "count": count})
    return count

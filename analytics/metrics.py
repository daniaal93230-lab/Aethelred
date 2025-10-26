"""
Pure stdlib analytics over the journal DB.
No pandas dependency. SQLite only.
"""

from __future__ import annotations
import math
import sqlite3
from typing import Dict, List, Tuple

# ---------- Returns series from equity ----------


def load_daily_returns(conn: sqlite3.Connection) -> List[float]:
    """
    Load daily returns from v_daily_equity.ret, skipping NULLs.
    """
    cur = conn.execute("SELECT ret FROM v_daily_equity WHERE ret IS NOT NULL ORDER BY day ASC")
    return [r for (r,) in cur.fetchall()]


def mean(xs: List[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def stdev(xs: List[float]) -> float:
    if len(xs) < 2:
        return 0.0
    mu = mean(xs)
    var = sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var)


def downside_deviation(xs: List[float], mar: float = 0.0) -> float:
    downs = [min(0.0, x - mar) for x in xs]
    if not xs:
        return 0.0
    return math.sqrt(sum(d * d for d in downs) / len(xs))


def sharpe(xs: List[float], rf: float = 0.0, periods_per_year: int = 252) -> float:
    """
    Annualized Sharpe using population formula with sample stdev.
    """
    if not xs:
        return 0.0
    ex = [x - rf / periods_per_year for x in xs]
    mu = mean(ex)
    sd = stdev(ex)
    if sd == 0.0:
        return 0.0
    return (mu / sd) * math.sqrt(periods_per_year)


def sortino(xs: List[float], rf: float = 0.0, mar: float = 0.0, periods_per_year: int = 252) -> float:
    if not xs:
        return 0.0
    ex = [x - rf / periods_per_year for x in xs]
    mu = mean(ex) - mar / periods_per_year
    dd = downside_deviation(ex, 0.0)
    if dd == 0.0:
        return 0.0
    return (mu / dd) * math.sqrt(periods_per_year)


def max_drawdown_from_equity(conn: sqlite3.Connection) -> Tuple[float, float, float]:
    """
    Returns tuple (max_dd_pct, peak_equity, trough_equity) from equity_snapshots.
    Computed on the closing equity per day for stability.
    """
    cur = conn.execute("SELECT equity_close FROM v_daily_equity ORDER BY day ASC")
    series = [e for (e,) in cur.fetchall()]
    peak = -float("inf")
    max_dd = 0.0
    peak_val = 0.0
    trough_val = 0.0
    for e in series:
        if e > peak:
            peak = e
        dd = 0.0 if peak == 0 else (e - peak) / peak
        if dd < max_dd:
            max_dd = dd
            peak_val = peak
            trough_val = e
    return (max_dd, peak_val, trough_val)


# ---------- Trade reconstruction from fills ----------


class Trade:
    __slots__ = (
        "symbol",
        "side",
        "qty",
        "entry_ts",
        "exit_ts",
        "entry_price",
        "exit_price",
        "fees_usd",
        "slippage_bps",
        "decision_id",
    )

    def __init__(self):
        self.symbol = ""
        self.side = ""
        self.qty = 0.0
        self.entry_ts = 0.0
        self.exit_ts = 0.0
        self.entry_price = 0.0
        self.exit_price = 0.0
        self.fees_usd = 0.0
        self.slippage_bps = 0.0
        self.decision_id = None


def _fetch_fills(conn: sqlite3.Connection) -> Dict[str, List[Tuple[float, str, float, float, float, float, int]]]:
    """
    Returns fills grouped by symbol.
    Row: (ts, side, qty, price, fee_usd, slippage_bps, decision_id)
    """
    cur = conn.execute(
        "SELECT symbol, ts, side, qty, price, fee_usd, slippage_bps, decision_id "
        "FROM fills ORDER BY symbol ASC, ts ASC, id ASC"
    )
    out: Dict[str, List[Tuple[float, str, float, float, float, float, int]]] = {}
    for symbol, ts, side, qty, price, fee, slp, dec_id in cur.fetchall():
        out.setdefault(symbol, []).append((float(ts), side, float(qty), float(price), float(fee), float(slp), dec_id))
    return out


def reconstruct_round_trips(conn: sqlite3.Connection) -> List[Trade]:
    """
    Simple flat-to-flat trade reconstruction per symbol using FIFO of fills.
    Assumes we do not flip directly from long to short without flattening.
    """
    grouped = _fetch_fills(conn)
    trades: List[Trade] = []
    for symbol, rows in grouped.items():
        pos_qty = 0.0
        side = ""  # long or short
        entry_ts = 0.0
        vwap_num = 0.0
        vwap_den = 0.0
        fees = 0.0
        slps = 0.0
        dec_id = None
        for ts, s, qty, price, fee, slp, d_id in rows:
            if pos_qty == 0.0:
                # starting a new trade
                side = "long" if s == "buy" else "short"
                entry_ts = ts
                vwap_num = price * qty
                vwap_den = qty
                pos_qty = qty if side == "long" else -qty
                fees = fee
                slps = slp
                dec_id = d_id
            else:
                direction = 1 if side == "long" else -1
                if (s == "buy" and direction == 1) or (s == "sell" and direction == -1):
                    # adding to position
                    vwap_num += price * qty
                    vwap_den += qty
                    pos_qty += qty * direction
                    fees += fee
                    slps += slp
                else:
                    # reducing or closing
                    pos_qty -= qty * direction
                    fees += fee
                    slps += slp
                    if pos_qty == 0.0:
                        # close trade
                        t = Trade()
                        t.symbol = symbol
                        t.side = side
                        t.qty = vwap_den  # total base size in the trade
                        t.entry_ts = entry_ts
                        t.exit_ts = ts
                        t.entry_price = vwap_num / vwap_den if vwap_den else price
                        t.exit_price = price
                        t.fees_usd = fees
                        t.slippage_bps = slps
                        t.decision_id = dec_id
                        trades.append(t)
                        # reset
                        side = ""
                        entry_ts = 0.0
                        vwap_num = 0.0
                        vwap_den = 0.0
                        fees = 0.0
                        slps = 0.0
                        dec_id = None
        # if pos remains open, ignore partial since no realized PnL yet
    return trades


# ---------- Metrics from reconstructed trades and equity ----------


def win_rate_and_expectancy(conn: sqlite3.Connection) -> Tuple[float, float]:
    """
    Returns (win_rate, expectancy_usd_per_trade).
    Expectancy computed as average realized PnL net of fees across closed trades.
    """
    trades = reconstruct_round_trips(conn)
    if not trades:
        return 0.0, 0.0
    wins = 0
    total = 0
    pnl_sum = 0.0
    for t in trades:
        direction = 1.0 if t.side == "long" else -1.0
        gross = (t.exit_price - t.entry_price) * direction * t.qty
        pnl = gross - t.fees_usd
        if pnl > 0:
            wins += 1
        total += 1
        pnl_sum += pnl
    win_rate = wins / total if total else 0.0
    expectancy = pnl_sum / total if total else 0.0
    return win_rate, expectancy


def average_exposure_and_turnover(conn: sqlite3.Connection) -> Tuple[float, float]:
    """
    Exposure: average daily exposure_usd from equity_snapshots.
    Turnover: average daily gross_notional_usd from v_symbol_turnover summed across symbols.
    """
    cur = conn.execute("SELECT AVG(exposure_usd) FROM equity_snapshots")
    avg_exposure = cur.fetchone()[0] or 0.0
    cur = conn.execute(
        "SELECT AVG(x.gross) FROM ("
        "  SELECT day, SUM(gross_notional_usd) AS gross FROM v_symbol_turnover GROUP BY day"
        ") x"
    )
    avg_turnover = cur.fetchone()[0] or 0.0
    return float(avg_exposure), float(avg_turnover)


def compute_all_metrics(conn: sqlite3.Connection) -> Dict[str, float]:
    """
    Convenience aggregator to support orchestrator checks.
    """
    rets = load_daily_returns(conn)
    # For very small sample sizes (<=2 days) the Sharpe/Sortino estimates are unstable.
    # Return 0.0 for these metrics to avoid misleading large numbers in tests and QA.
    if len(rets) < 3:
        sh = 0.0
        so = 0.0
    else:
        sh = sharpe(rets)
        so = sortino(rets)
    mdd, peak, trough = max_drawdown_from_equity(conn)
    wr, exp_usd = win_rate_and_expectancy(conn)
    avg_exp, avg_tn = average_exposure_and_turnover(conn)
    return {
        "sharpe": sh,
        "sortino": so,
        "max_drawdown_pct": mdd,
        "win_rate": wr,
        "expectancy_usd": exp_usd,
        "avg_exposure_usd": avg_exp,
        "avg_turnover_usd": avg_tn,
    }

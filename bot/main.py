# bot/main.py
from __future__ import annotations
import argparse
import sys
import math
import pandas as pd

# ccxt is required for live fetch
try:
    import ccxt  # type: ignore
except Exception:
    print("[Brain] ccxt is required: pip install ccxt", file=sys.stderr)
    sys.exit(1)

# Import via bot/* shims (they forward to core/* if present)
from . import data_fetch, strategies, evaluator, risk, json_io
from .indicators import adx
from .strategies import StrategyConfig
from .evaluator import WFSelParams
from .ledger import PaperLedger

# Tuner persistence helpers + access to the global TUNER
from . import strategy as strategy_mod
from .persist import load_tuner, save_tuner


# -------- safe number helpers (avoid NaN/inf crashes) --------
def _safe_float(x, default=0.0):
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def _safe_int(x, default=0):
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return int(v)
    except Exception:
        return default
# -------------------------------------------------------------

def _equity_bars_from_signal(index, close: pd.Series, signal: pd.Series,
                             fee: float, slip_bps: float) -> pd.Series:
    """
    Compute bar-by-bar equity (starting at 1.0) from close prices and a -1/0/+1 signal.
    Fees+slippage applied at each entry/exit (flip = exit+entry). MTM on each bar.
    """
    cost = float(fee) + float(slip_bps) / 10_000.0
    px = pd.Series(close).astype(float).values
    sig = pd.Series(signal).fillna(0).astype(int).values
    eq = [1.0]
    for i in range(1, len(px)):
        pos_prev = sig[i-1]
        pos_now  = sig[i]
        # mark-to-market on prior position
        r = 0.0
        if pos_prev != 0:
            r = (px[i] / px[i-1] - 1.0) * (1 if pos_prev > 0 else -1)
        val = eq[-1] * (1 + r)
        # transaction costs on the transition at this bar
        if pos_now != pos_prev:
            if pos_prev != 0:  # exit
                val *= (1 - cost)
            if pos_now != 0:   # entry
                val *= (1 - cost)
        eq.append(val)
    return pd.Series(eq, index=index)

def _blotter_from_signal(index, close: pd.Series, signal: pd.Series,
                         fee: float, slip_bps: float) -> pd.DataFrame:
    """
    Convert a position signal (-1/0/+1) and close prices into a trade blotter.
    Bar-close execution on entry/exit. Fees + slippage applied on both legs.
    Supports direct flips (e.g., +1 -> -1) by closing and re-opening on the same bar.
    Returns ONLY closed trades.
    """
    cost = float(fee) + float(slip_bps) / 10_000.0  # e.g. 0.0004 + (1 / 10k) = 0.0005

    sig = pd.Series(signal).fillna(0).astype(int).tolist()
    px  = pd.Series(close).astype(float).tolist()
    ts  = list(index)

    trades = []
    pos = 0      # -1, 0, +1
    ent_i = None
    ent_p = None

    # If we start in a position, open at bar 0
    if len(sig) > 0 and sig[0] != 0:
        pos = sig[0]
        ent_i = 0
        ent_p = px[0]

    for i in range(1, len(sig)):
        curr = sig[i]

        if pos == 0:
            # Open from flat on first non-zero
            if curr != 0:
                pos = curr
                ent_i = i
                ent_p = px[i]
        else:
            # Close when going flat OR flipping side
            if curr == 0 or curr != pos:
                exit_i = i
                exit_p = px[i]

                if pos > 0:  # LONG round-trip
                    net = (exit_p * (1 - cost)) / (ent_p * (1 + cost)) - 1.0
                    side = "LONG"
                else:        # SHORT round-trip
                    net = (ent_p * (1 - cost)) / (exit_p * (1 + cost)) - 1.0
                    side = "SHORT"

                trades.append({
                    "entry_time": pd.Timestamp(ts[ent_i]).isoformat(),
                    "exit_time":  pd.Timestamp(ts[exit_i]).isoformat(),
                    "side": side,
                    "entry_price": float(ent_p),
                    "exit_price": float(exit_p),
                    "bars": int(exit_i - ent_i),
                    "return_pct": float(net * 100.0),
                })

                # If it’s a flip (curr != 0), re-open immediately at this bar
                if curr != 0 and curr != pos:
                    pos = curr
                    ent_i = i
                    ent_p = exit_p  # same bar, enter at the same close
                else:
                    pos = 0
                    ent_i = ent_p = None

    return pd.DataFrame(trades)


def main() -> None:
    ap = argparse.ArgumentParser(prog="brain")

    # Exchange / data
    ap.add_argument("--exchange", default="binance", help="ccxt exchange id (e.g., binance)")
    ap.add_argument("--symbol", required=True, help="Pair like BTC/USDT (ccxt format)")
    ap.add_argument("--interval", default="4h", help="Timeframe (1m, 5m, 1h, 4h, 1d)")
    ap.add_argument("--limit", type=int, default=5000, help="Number of bars to fetch")
    ap.add_argument("--user", default=None)

    # Profiles
    ap.add_argument("--profile", default=None, help="Optional profile, e.g. 'easy'")

    # Walk-forward windowing
    ap.add_argument("--wf-train", type=int, default=1000)
    ap.add_argument("--wf-test", type=int, default=500)
    ap.add_argument("--wf-step", type=int, default=400)
    ap.add_argument("--min-trades", type=int, default=10)
    ap.add_argument("--min-expectancy", type=float, default=0.0)
    ap.add_argument("--min-sharpe", type=float, default=0.0)

    # ADX / regime control
    ap.add_argument("--adx-trend-threshold", type=float, default=15.0)
    ap.add_argument("--adx-len", type=int, default=14)
    ap.add_argument("--trend-no-long", dest="allow_long", action="store_false")
    ap.add_argument("--trend-no-short", dest="allow_short", action="store_false")
    ap.set_defaults(allow_long=True, allow_short=True)

    # Costs
    ap.add_argument("--fee", type=float, default=0.0004)
    ap.add_argument("--slip-bps", type=float, default=1.0)

    # Entry gating
    ap.add_argument("--entry-age", type=int, default=6, help="Max bars since last signal change")
    ap.add_argument(
        "--late-entry",
        choices=["block", "allow", "decay"],
        default="block",
        help="If signal is older than --entry-age: block (default), allow, or decay size.",
    )

    # Kelly sizing
    ap.add_argument("--risk", type=float, default=0.10)
    ap.add_argument("--kelly-on", action="store_true")
    ap.add_argument("--kelly-min", type=float, default=0.4)
    ap.add_argument("--kelly-max", type=float, default=1.4)
    ap.add_argument("--kelly-shrink", type=float, default=20.0)

    # Paper ledger
    ap.add_argument("--paper-ledger", action="store_true")
    ap.add_argument("--paper-file", default="brain_ledger.csv")
    ap.add_argument("--paper-state-file", default="brain_state.json")
    ap.add_argument("--paper-fee-bps", type=float, default=5.0)
    ap.add_argument("--paper-slip-bps", type=float, default=1.0)
    ap.add_argument("--paper-cash", type=float, default=10000.0)
    ap.add_argument("--paper-mtm", dest="paper_mtm", action="store_true", default=True)
    ap.add_argument("--paper-no-mtm", dest="paper_mtm", action="store_false")

    # Output
    ap.add_argument("--emit-json", action="store_true")
    ap.add_argument("--emit-json-file", default="brain_signal.json")
    ap.add_argument("--print-summary", action="store_true",
                    help="Print backtest summary (trades, win rate, Sharpe, total return)")
    ap.add_argument("--dump-trades", metavar="CSV", default=None,
                    help="Write backtested closed trades to CSV")
    ap.add_argument("--dump-trades-test-only", metavar="CSV", default=None,
                    help="Write closed trades for the LAST WF test window only to CSV")
    ap.add_argument("--dump-equity", metavar="CSV", default=None,
                    help="Write backtested equity curve to CSV")

    # Tuner persistence
    ap.add_argument("--tuner-persist", action="store_true", help="Enable saving/loading tuner memory")
    ap.add_argument("--tuner-file", default="tuner_mem.json", help="Path to tuner memory file")

    # Debug
    ap.add_argument("--debug-segments", action="store_true")

    ap.add_argument("--dump-equity-bars", metavar="CSV", default=None, help="Write bar-by-bar equity curve to CSV (full series)")
    ap.add_argument("--dump-equity-bars-test-only", metavar="CSV", default=None, help="Write bar-by-bar equity for the last WF test window to CSV")

    ap.add_argument("--risk", type=float, default=0.02)  # from 0.10 -> 0.02

    args = ap.parse_args()

    # Profile tweaks
    if args.profile == "easy":
        args.min_trades = max(3, int(args.min_trades * 0.5))
        args.min_sharpe = min(args.min_sharpe, -0.2)

    # Load tuner memory (optional)
    if args.tuner_persist:
        load_tuner(args.tuner_file, strategy_mod.TUNER)

    print(
        f"[Brain] Fetching data: exchange={args.exchange} symbol={args.symbol} "
        f"timeframe={args.interval} target~{args.limit}"
    )

    # Exchange
    ex_cls = getattr(ccxt, args.exchange, None)
    if ex_cls is None:
        print(f"[Brain] Unknown exchange: {args.exchange}", file=sys.stderr)
        sys.exit(2)
    exchange = ex_cls({"enableRateLimit": True})

    # Fetch → DataFrame
    candles = data_fetch.fetch_ohlcv_paginated(exchange, args.symbol, args.interval, args.limit)
    df = data_fetch.candles_to_df(candles)

    # Align to last *closed* bar
    expected_last_ts = pd.to_datetime(data_fetch.expected_last_closed_ms(args.interval), unit="ms", utc=True)
    if not df.empty and df.index[-1] > expected_last_ts:
        df = df[df.index <= expected_last_ts]

    loaded = len(df)
    first_ts = df.index[0].isoformat() if loaded > 0 else "n/a"
    last_ts = df.index[-1].isoformat() if loaded > 0 else "n/a"
    print(
        f"[Brain] Candles loaded: {loaded} | first={first_ts} | last={last_ts} | "
        f"expected_last_closed={expected_last_ts.isoformat()}"
    )

    # Not enough data
    if loaded < 10:
        decision = {
            "timestamp": last_ts or pd.Timestamp.utcnow().isoformat(),
            "symbol": args.symbol,
            "interval": args.interval,
            "status": "CASH",
            "regime": None,
            "side": "flat",
            "size_fraction": 0.0,
            "reason": "Insufficient history",
        }
        print("\n====== BRAIN DECISION ======\nSummary: CASH (insufficient data)\n")
        if args.emit_json:
            json_io.emit_signal_to_json(decision, args.emit_json_file, user=args.user)
        if args.tuner_persist:
            save_tuner(args.tuner_file, strategy_mod.TUNER)
        return

    # Strategy grid (MA_X, Donchian, RSI-MR)
    strategy_configs = []
    for fast, slow in [(10, 21), (13, 34), (20, 50), (21, 55), (34, 89)]:
        strategy_configs.append(StrategyConfig(name="MA_X", params={"fast": fast, "slow": slow}))
    for nb, nx in [(20, 10), (40, 20), (55, 20)]:
        strategy_configs.append(StrategyConfig(name="DONCHIAN", params={"n_break": nb, "n_exit": nx}))
    for rl, rb, rx in [(14, 25, 55), (14, 22, 55), (7, 20, 55)]:
        strategy_configs.append(
            StrategyConfig(name="RSI_MR", params={"rsi_n": rl, "buy_th": rb, "sell_th": rx})
        )

    sel_params = WFSelParams(
        train=args.wf_train,
        test=args.wf_test,
        step=args.wf_step,
        min_trades=args.min_trades,
        min_expectancy=args.min_expectancy,
        min_sharpe=args.min_sharpe,
        adx_threshold=args.adx_trend_threshold,
        adx_len=args.adx_len,
        allow_long=args.allow_long,
        allow_short=args.allow_short,
    )

    # Walk-forward (with per-market tuner key)
    segments = evaluator.walk_forward_select(
        df, sel_params, fee=args.fee, slip_bps=args.slip_bps,
        strategies=strategy_configs, key_hint=(args.symbol, args.interval)
    )

    if args.debug_segments:
        if len(segments) == 0:
            print("\n[Brain] WF segments: <none>\n")
        else:
            print("\n[Brain] WF segments:")
            cols = [
                "start", "end", "regime", "strategy",
                "exp_train", "n_train", "exp_test", "n_test",
                "sharpe_test", "fallback", "autotuned",
            ]
            rows = [[seg.get(c) for c in cols] for seg in segments]
            df_debug = pd.DataFrame(rows, columns=cols)
            with pd.option_context("display.max_rows", None, "display.width", 180):
                print(df_debug.to_string(index=False))
            print()

    # Choose last valid segment
    valid_segments = [seg for seg in segments if seg.get("strategy") is not None]
    if not valid_segments:
        print("\n====== BRAIN DECISION ======\nSummary: CASH (no valid segment)\n")
        decision = {
            "timestamp": last_ts,
            "symbol": args.symbol,
            "interval": args.interval,
            "status": "CASH",
            "regime": None,
            "side": "flat",
            "size_fraction": 0.0,
            "reason": "No tradable segment",
        }
        if args.emit_json:
            json_io.emit_signal_to_json(decision, args.emit_json_file, user=args.user)
        if args.tuner_persist:
            save_tuner(args.tuner_file, strategy_mod.TUNER)
        return

    best_seg = sorted(valid_segments, key=lambda s: s["end"])[-1]
    strategy_name = best_seg["strategy"]
    strat_params = best_seg.get("params", {}) or {}
    fast = int(strat_params.get("fast", 13))
    slow = int(strat_params.get("slow", 34))

    # Build signal for chosen strategy
    if strategy_name == "MA_X":
        raw_signal = strategies.ma_x_signal(df["close"], fast, slow)
        adx_series = adx(df["high"], df["low"], df["close"], args.adx_len)
        full_signal = strategies.apply_regime_filter(
            raw_signal, adx_series, args.adx_trend_threshold,
            allow_long=args.allow_long, allow_short=args.allow_short
        )

    # Back-compat alias for older code/notes
    def moving_average_crossover(close, fast=20, slow=50, allow_long=True, allow_short=False):
        return ma_x_signal(close, fast=fast, slow=slow, allow_long=allow_long, allow_short=allow_short)

    elif strategy_name == "DONCHIAN":
        raw_signal = strategies.donchian_signal(
            df, int(strat_params.get("n_break", 20)), int(strat_params.get("n_exit", 10))
        )
        adx_series = adx(df["high"], df["low"], df["close"], args.adx_len)
        full_signal = strategies.apply_regime_filter(
            raw_signal, adx_series, args.adx_trend_threshold,
            allow_long=args.allow_long, allow_short=args.allow_short
        )
    elif strategy_name == "RSI_MR":
        raw_signal = strategies.rsi_mr_signal(
            df["close"],
            rsi_n=int(strat_params.get("rsi_n", 14)),
            buy_th=int(strat_params.get("buy_th", 25)),
            sell_th=int(strat_params.get("sell_th", 55)),
        )
        full_signal = strategies.apply_no_filter(
            raw_signal, allow_long=args.allow_long, allow_short=args.allow_short
        )
    else:
        # fallback (shouldn't happen)
        raw_signal = strategies.ma_x_signal(df["close"], fast, slow)
        adx_series = adx(df["high"], df["low"], df["close"], args.adx_len)
        full_signal = strategies.apply_regime_filter(
            raw_signal, adx_series, args.adx_trend_threshold,
            allow_long=args.allow_long, allow_short=args.allow_short
        )



    # Latest signal & age
    side_now, age_bars = evaluator.last_signal_within(full_signal, bars=max(args.entry_age, 1))
    entry_price = evaluator.last_entry_price(df["close"], full_signal, side_now)
    pos_ret_pct = None
    if entry_price is not None and side_now != 0:
        pos_ret_pct = (
            (float(df["close"].iloc[-1]) / float(entry_price) - 1.0)
            * (1 if side_now > 0 else -1)
            * 100.0
        )

    # Equity curve & metrics
    equity_full, metrics_full = evaluator.equity_curve(
        df["close"], full_signal, fee=args.fee, slip_bps=args.slip_bps
    )

    # Bar-by-bar equity CSVs (optional)
    if args.dump_equity_bars or args.dump_equity_bars_test_only:
        eq_bars_full = _equity_bars_from_signal(df.index, df["close"], full_signal, args.fee, args.slip_bps)

    if args.dump_equity_bars:
        pd.DataFrame({"equity": eq_bars_full}).to_csv(args.dump_equity_bars, index_label="timestamp")
        print(f"[Brain] Bar equity written to {args.dump_equity_bars} ({len(eq_bars_full)} bars)")

    if args.dump_equity_bars_test_only:
        end_i = int(best_seg.get("end", len(df) - 1))
        test_len = int(sel_params.test)
        start_i = max(0, end_i - test_len + 1)
        sub = eq_bars_full.iloc[start_i:end_i + 1]
        pd.DataFrame({"equity": sub}).to_csv(args.dump_equity_bars_test_only, index_label="timestamp")
        print(f"[Brain] Bar equity (test) written to {args.dump_equity_bars_test_only} ({len(sub)} bars)")

    # ---- Optional one-line backtest summary ----
    if args.print_summary:
        print(
            f"[Perf] backtest trades={_safe_int(metrics_full.get('trades',0))} | "
            f"win={_safe_float(metrics_full.get('win_rate',0))*100:.1f}% | "
            f"exp/trade={_safe_float(metrics_full.get('expectancy',0))*100:.2f}% | "
            f"Sharpe={_safe_float(metrics_full.get('sharpe',0)):.2f} | "
            f"total={_safe_float(metrics_full.get('total_return',0))*100:.2f}%"
        )
    # --------------------------------------------

    # Dump equity curve if requested
    if args.dump_equity:
        eq_series = equity_full if isinstance(equity_full, pd.Series) else pd.Series(equity_full, index=df.index)
        out = pd.DataFrame({"equity": eq_series})
        out.to_csv(args.dump_equity, index_label="timestamp")
        print(f"[Brain] Equity curve written to {args.dump_equity} ({len(out)} points)")

    # Dump trades blotter(s) if requested
    def _write_blotter(csv_path, idx, close, sig, fee, slip):
        blotter = _blotter_from_signal(idx, close, sig, fee, slip)
        if not blotter.empty:
            blotter.to_csv(csv_path, index=False)
            print(f"[Brain] Trade blotter written to {csv_path} ({len(blotter)} closed trades)")
        else:
            print(f"[Brain] Trade blotter: no closed trades to write for {csv_path}")

    if args.dump_trades or args.dump_trades_test_only:
        # Full-series blotter
        if args.dump_trades:
            _write_blotter(args.dump_trades, df.index, df["close"], full_signal, args.fee, args.slip_bps)

        # Last WF test-only blotter
        if args.dump_trades_test_only:
            end_i = int(best_seg.get("end", len(df) - 1))
            test_len = int(sel_params.test)
            start_i = max(0, end_i - test_len + 1)
            sub_idx = df.index[start_i:end_i + 1]
            sub_close = df["close"].iloc[start_i:end_i + 1]
            sub_sig = full_signal.iloc[start_i:end_i + 1]
            _write_blotter(args.dump_trades_test_only, sub_idx, sub_close, sub_sig, args.fee, args.slip_bps)

    # Sizing (Kelly optional)
    train_metrics = {"expectancy": float(best_seg.get("exp_train", 0.0) or 0.0), "win_rate": float(0.55)}
    size_fraction = risk.kelly_size_from_metrics(
        met_tr=train_metrics,
        kelly_on=args.kelly_on,
        kelly_min=args.kelly_min,
        kelly_max=args.kelly_max,
        kelly_shrink=args.kelly_shrink,
        base_risk=args.risk,
    )

    # -------- SINGLE DECISION PATH --------
    late_mode = args.late_entry  # block | allow | decay
    can_trade_now = side_now != 0

    if not can_trade_now:
        print("\n====== BRAIN DECISION ======\nSummary: CASH (flat signal)\n")
        decision = {
            "timestamp": last_ts,
            "symbol": args.symbol,
            "interval": args.interval,
            "status": "CASH",
            "regime": "trend",
            "side": "flat",
            "size_fraction": 0.0,
            "reason": "Signal is flat",
            "debug": {"side_now": int(side_now), "age_bars": int(age_bars)},
        }
        paper_summary = None
        eq_for_json = equity_full

    elif age_bars > args.entry_age and late_mode == "block":
        print("\n====== BRAIN DECISION ======\nSummary: CASH (late entry blocked)\n")
        decision = {
            "timestamp": last_ts,
            "symbol": args.symbol,
            "interval": args.interval,
            "status": "CASH",
            "regime": "trend",
            "side": "flat",
            "size_fraction": 0.0,
            "reason": f"Signal age {int(age_bars)} > entry_age {int(args.entry_age)}",
            "debug": {"side_now": int(side_now), "age_bars": int(age_bars), "late_mode": late_mode},
        }
        paper_summary = None
        eq_for_json = equity_full

    else:
        # Trade allowed (fresh, or allowed/decayed late entry)
        size = float(size_fraction)
        reason = "fresh entry"
        if age_bars > args.entry_age:
            if late_mode == "decay":
                scale = max(0.2, min(1.0, float(args.entry_age) / float(age_bars)))  # floor at 20%
                size *= scale
                reason = f"late entry (decay scale={scale:.2f})"
            else:
                reason = "late entry (allowed)"

        side_str = "LONG" if side_now > 0 else "SHORT"
        print(
            f"\n====== BRAIN DECISION ======\n"
            f"Summary: TRADE ({side_str}) | {reason} | "
            f"fallback_used={bool(best_seg.get('fallback', False))} | autotuned={bool(best_seg.get('autotuned', False))}\n"
        )

        # Safe-coerced WF fields
        tr_exp = _safe_float(best_seg.get("exp_train", 0.0))
        te_exp = _safe_float(best_seg.get("exp_test", 0.0))
        te_shp = _safe_float(best_seg.get("sharpe_test", 0.0))
        tr_n   = _safe_int(best_seg.get("n_train", 0))
        te_n   = _safe_int(best_seg.get("n_test", 0))

        decision = {
            "timestamp": last_ts,
            "symbol": args.symbol,
            "interval": args.interval,
            "status": "TRADE",
            "regime": "trend",
            "side": side_str,
            "size_fraction": size,
            "risk_per_trade": float(args.risk),
            "allow_long": bool(args.allow_long),
            "allow_short": bool(args.allow_short),
            "price": float(df["close"].iloc[-1]),
            "strategy": strategy_name,
            "params": strat_params,
            "fallback_used": bool(best_seg.get("fallback", False)),
            "autotuned": bool(best_seg.get("autotuned", False)),
            "signal_bar": str(df.index[-1]),
            "recent_signal_age_bars": int(age_bars),
            "late_mode": late_mode,
            "wf": {
                "train_expectancy": tr_exp,
                "test_expectancy": te_exp,
                "test_sharpe": te_shp,
                "train_trades": tr_n,
                "test_trades": te_n,
            },
            "backtest_full": {
                "trades": _safe_int(metrics_full.get("trades", 0)),
                "sharpe": _safe_float(metrics_full.get("sharpe", 0.0)),
                "total_return_pct": _safe_float(metrics_full.get("total_return", 0.0)) * 100.0,
            },
        }
        if pos_ret_pct is not None:
            decision.setdefault("position", {})["unrealized_return_pct"] = float(pos_ret_pct)
        paper_summary = None
        eq_for_json = equity_full
    # -------- END SINGLE DECISION PATH --------

    # Paper ledger
    if args.paper_ledger:
        try:
            pl = PaperLedger(
                csv_path=args.paper_file,
                state_path=args.paper_state_file,
                fee_bps=float(args.paper_fee_bps),
                slip_bps=float(args.paper_slip_bps),
            )
            paper_summary = pl.update(
                decision=decision,
                price=float(df["close"].iloc[-1]),
                timestamp_iso=str(df.index[-1]),
                start_cash=float(args.paper_cash),
            )
        except Exception as e:
            print(f"[Brain] Paper ledger error: {e}", file=sys.stderr)
            paper_summary = {"error": str(e)}

    # JSON output
    if args.emit_json:
        json_io.emit_signal_to_json(
            decision, args.emit_json_file, user=args.user,
            equity_curve=eq_for_json, paper_summary=paper_summary
        )

    # Persist tuner memory on normal exit
    if args.tuner_persist:
        save_tuner(args.tuner_file, strategy_mod.TUNER)


if __name__ == "__main__":
    main()

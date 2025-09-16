# bot/tune.py
# Run: python -m bot.tune --symbol BTC/USDT --interval 1h --strategy donchian --since-years 2

import argparse, time
import pandas as pd
from fetch_market_data import fetch_data
from core.engine import add_atr, add_htf_ema_flag, add_adx, build_signals, backtest_long_only
from bot.brain import apply_cost_guard, _largest_window  # reuse helpers
from bot.brain import build_donchian_short, backtest_short_only  # for short strategy, if needed

def _since_years(years: int) -> int:
    return int(time.time()*1000) - int(years*365*24*60*60*1000)

def score(stats: dict) -> float:
    # same scoring as brain
    tr = stats.get("total_return_pct", 0.0) or 0.0
    dd = stats.get("max_drawdown_pct", 0.0) or 0.0
    wr = stats.get("win_rate_pct", 0.0) or 0.0
    nt = stats.get("num_trades", 0) or 0
    s  = tr - 0.7*dd + 0.2*wr
    if nt < 3: s -= 30
    return round(s, 2)

def walk_forward(df: pd.DataFrame, strategy: str, grid: list[dict],
                 train_bars=4000, test_bars=800, min_atr_pct=0.40):
    """
    Sliding window: pick best grid on train, evaluate on next test.
    """
    i, results = 0, []
    while i + train_bars + test_bars <= len(df):
        train = df.iloc[i:i+train_bars].copy()
        test  = df.iloc[i+train_bars:i+train_bars+test_bars].copy()
        # indicators
        train = add_atr(train, 14); train = add_adx(train, 14)
        test  = add_atr(test, 14);  test  = add_adx(test, 14)

        # pick best on train
        best_s, best_p = -1e9, None
        for p in grid:
            if strategy == "donchian":
                sig = build_signals(train, "donchian_breakout", {"entry_n": p["entry_n"], "exit_n": p["exit_n"], "require_htf": False})
                sig = apply_cost_guard(sig, min_atr_pct)
                st  = backtest_long_only(sig, fraction_per_trade=0.25)
            elif strategy == "rsi":
                sig = build_signals(train, "rsi_mean_reversion", {"rsi_len": p["rsi_len"], "rsi_buy": p["rsi_buy"], "rsi_exit": p["rsi_exit"], "require_htf": False})
                sig = apply_cost_guard(sig, min_atr_pct)
                st  = backtest_long_only(sig, fraction_per_trade=0.25)
            else:
                raise ValueError("unsupported strategy")
            sc = score(st)
            if sc > best_s:
                best_s, best_p = sc, p

        # evaluate best on test
        if strategy == "donchian":
            sig = build_signals(test, "donchian_breakout", {"entry_n": best_p["entry_n"], "exit_n": best_p["exit_n"], "require_htf": False})
            sig = apply_cost_guard(sig, min_atr_pct)
            st  = backtest_long_only(sig, fraction_per_trade=0.25)
        else:
            sig = build_signals(test, "rsi_mean_reversion", {"rsi_len": best_p["rsi_len"], "rsi_buy": best_p["rsi_buy"], "rsi_exit": best_p["rsi_exit"], "require_htf": False})
            sig = apply_cost_guard(sig, min_atr_pct)
            st  = backtest_long_only(sig, fraction_per_trade=0.25)

        results.append({"i": i, "train_score": best_s, "params": best_p, "test_stats": st})
        i += test_bars
    return results

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="BTC/USDT")
    ap.add_argument("--interval", default="1h")
    ap.add_argument("--since-years", type=int, default=2)
    ap.add_argument("--strategy", choices=["donchian","rsi"], default="donchian")
    args = ap.parse_args()

    since = _since_years(args.since_years)
    df = fetch_data(args.symbol, args.interval, since=since, max_bars=None)
    df = df.dropna().reset_index(drop=True)

    # simple grids
    if args.strategy == "donchian":
        grid = [{"entry_n": e, "exit_n": x} for e in range(25, 61, 5) for x in range(8, 21, 4)]
    else:
        grid = [{"rsi_len": rl, "rsi_buy": rb, "rsi_exit": rx}
                for rl in range(10, 19, 2) for rb in (20,25,30,35) for rx in (50,55,60,65)]

    res = walk_forward(df, args.strategy, grid, train_bars=4000, test_bars=800, min_atr_pct=0.40)

    # aggregate
    tests = [r["test_stats"] for r in res]
    if not tests:
        print("Not enough data for walk-forward windows.")
        return

    fin = pd.DataFrame([{
        "ret": t["total_return_pct"], "dd": t["max_drawdown_pct"],
        "win": t["win_rate_pct"], "trades": t["num_trades"]
    } for t in tests])

    print(f"Windows: {len(res)}")
    print(f"Avg test return: {fin['ret'].mean():.2f}%  |  Avg DD: {fin['dd'].mean():.2f}%  |  "
          f"Win%: {fin['win'].mean():.1f}%  |  Trades/window: {fin['trades'].mean():.1f}")
    print("\nTop 3 train picks (by score):")
    top3 = sorted(res, key=lambda r: r["train_score"], reverse=True)[:3]
    for r in top3:
        print(f"- score {r['train_score']}  params {r['params']}  test_ret {r['test_stats']['total_return_pct']}%")

if __name__ == "__main__":
    main()

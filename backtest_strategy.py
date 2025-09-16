# backtest_strategy.py
# Three strategies in one file: "ema_crossover", "rsi_mean_reversion", "donchian_breakout"
import pandas as pd
from fetch_market_data import fetch_data  # expects fetch_data(symbol, interval, limit)

# ================== CONFIG ==================
STRATEGY = "rsi_mean_reversion"   # "ema_crossover" | "rsi_mean_reversion" | "donchian_breakout"

START_BALANCE = 100.0
FRACTION_PER_TRADE = 0.33         # 1/3 of balance per trade
FEE_RATE = 0.001                  # 0.10% per side
SLIPPAGE_BPS = 2                  # 0.02% per side
COOLDOWN_BARS = 2                 # sit out after SL

# Data
SYMBOL   = "BTCUSDT"
INTERVAL = "1h"
LIMIT    = 1200

# Higher timeframe filter
HTF_INTERVAL = "4h"
HTF_LIMIT    = 1500
HTF_EMA_LEN  = 200               # 4h 200-EMA trend filter

# Indicators (per strategy)
# ema_crossover
EMA_SHORT = 10
EMA_LONG  = 50
EMA_CONFIRM_BARS = 2
EMA_MIN_GAP_PCT  = 0.20          # avoid micro crosses

# rsi_mean_reversion
RSI_LEN = 14
RSI_BUY = 32                     # buy when RSI below this, in uptrend
RSI_EXIT = 50                    # exit when RSI recovers above this

# donchian_breakout
DONCHIAN_ENTRY = 20              # break above 20-bar high
DONCHIAN_EXIT  = 10              # exit on close below 10-bar low

# Risk controls (ATR for SL/TP)
ATR_PERIOD  = 14
ATR_SL_MULT = 2.0
ATR_TP_MULT = 4.0
# ============================================


# ---------- Common indicators ----------
def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    prev_close = df["close"].shift(1)
    tr1 = (df["high"] - df["low"]).abs()
    tr2 = (df["high"] - prev_close).abs()
    tr3 = (df["low"] - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(window=period, min_periods=period).mean()
    return df

def add_htf_trend(df_base: pd.DataFrame) -> pd.DataFrame:
    htf = fetch_data(symbol=SYMBOL, interval=HTF_INTERVAL, limit=HTF_LIMIT)
    htf = htf.sort_values("timestamp").reset_index(drop=True)
    htf["HTF_EMA"] = htf["close"].ewm(span=HTF_EMA_LEN, adjust=False).mean()
    merged = pd.merge_asof(
        df_base.sort_values("timestamp"),
        htf[["timestamp", "HTF_EMA"]],
        on="timestamp",
        direction="backward"
    ).reset_index(drop=True)
    merged["HTF_TREND_UP"] = merged["close"] > merged["HTF_EMA"]
    return merged

# ---------- Strategy signal builders ----------
def build_signals_ema(df: pd.DataFrame) -> pd.DataFrame:
    df["EMA_short"] = df["close"].ewm(span=EMA_SHORT, adjust=False).mean()
    df["EMA_long"]  = df["close"].ewm(span=EMA_LONG,  adjust=False).mean()
    df["regime"] = 0
    df.loc[df["EMA_short"] > df["EMA_long"], "regime"] = 1
    df.loc[df["EMA_short"] < df["EMA_long"], "regime"] = -1

    # entry flag: confirmed regime + gap + HTF uptrend
    df["entry_long"] = False
    for i in range(len(df)):
        if i - EMA_CONFIRM_BARS < 1:
            continue
        # last N bars must be long regime; the bar before that short
        if not all(df["regime"].iloc[j] == 1 for j in range(i - EMA_CONFIRM_BARS + 1, i + 1)):
            continue
        if df["regime"].iloc[i - EMA_CONFIRM_BARS] != -1:
            continue
        s = float(df["EMA_short"].iloc[i])
        l = float(df["EMA_long"].iloc[i])
        if l == 0:
            continue
        gap = (s - l) / l * 100.0
        if gap < EMA_MIN_GAP_PCT:
            continue
        if not bool(df["HTF_TREND_UP"].iloc[i]):
            continue
        df.at[i, "entry_long"] = True

    # exit on opposite confirmed regime OR SL/TP in the engine
    df["exit_signal"] = False
    for i in range(len(df)):
        if i - EMA_CONFIRM_BARS < 1:
            continue
        if not all(df["regime"].iloc[j] == -1 for j in range(i - EMA_CONFIRM_BARS + 1, i + 1)):
            continue
        if df["regime"].iloc[i - EMA_CONFIRM_BARS] != 1:
            continue
        df.at[i, "exit_signal"] = True

    return df

def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1/length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/length, adjust=False).mean()
    rs = avg_gain / (avg_loss.replace(0, 1e-10))
    return 100 - (100 / (1 + rs))

def build_signals_rsi_mr(df: pd.DataFrame) -> pd.DataFrame:
    df["RSI"] = rsi(df["close"], RSI_LEN)
    # Entry: RSI below RSI_BUY and HTF uptrend (buy dips in an uptrend)
    df["entry_long"] = (df["RSI"] < RSI_BUY) & (df["HTF_TREND_UP"] == True)
    # Exit: RSI mean reversion back above RSI_EXIT (or SL/TP handled by engine)
    df["exit_signal"] = (df["RSI"] > RSI_EXIT)
    return df

def build_signals_donchian(df: pd.DataFrame) -> pd.DataFrame:
    # rolling highs/lows (shifted to avoid lookahead)
    df["don_high"] = df["high"].rolling(DONCHIAN_ENTRY).max().shift(1)
    df["don_low_exit"] = df["low"].rolling(DONCHIAN_EXIT).min().shift(1)
    # Entry if close breaks yesterday's N-bar high and HTF uptrend
    df["entry_long"] = (df["close"] > df["don_high"]) & (df["HTF_TREND_UP"] == True)
    # Exit on close below trailing exit low
    df["exit_signal"] = (df["close"] < df["don_low_exit"])
    return df

# ---------- Backtest engine (long-only) ----------
def backtest(df: pd.DataFrame) -> dict:
    balance = float(START_BALANCE)
    position_units = 0.0
    entry_price = None
    cash_out_at_entry = 0.0
    sl_price = None
    tp_price = None
    cooldown_until = -1

    trades = []
    equity_curve = []

    def exec_buy(close_price: float, i: int) -> bool:
        nonlocal balance, position_units, entry_price, cash_out_at_entry, sl_price, tp_price
        if balance <= 0:
            return False
        buy_px = float(close_price) * (1.0 + SLIPPAGE_BPS / 10_000.0)
        trade_cash = balance * FRACTION_PER_TRADE
        if trade_cash <= 0:
            return False
        units = trade_cash / buy_px
        if units <= 0:
            return False
        gross = units * buy_px
        fee = gross * FEE_RATE
        total_out = gross + fee
        if total_out > balance:
            scale = balance / total_out
            units *= scale
            gross = units * buy_px
            fee = gross * FEE_RATE
            total_out = gross + fee
        if total_out <= 0 or units <= 0:
            return False

        balance -= total_out
        position_units = float(units)
        entry_price = float(buy_px)
        cash_out_at_entry = float(total_out)

        # ATR-based SL/TP
        atr_val = df["ATR"].iloc[i]
        atr_val = float(atr_val) if pd.notna(atr_val) and atr_val > 0 else entry_price * 0.002
        sl_price_local = entry_price - ATR_SL_MULT * atr_val
        tp_price_local = entry_price + ATR_TP_MULT * atr_val
        sl_price = float(sl_price_local)
        tp_price = float(tp_price_local)

        trades.append({
            "action": "BUY",
            "price": round(entry_price, 8),
            "units": round(position_units, 12),
            "fee": round(float(fee), 6),
            "after_balance": round(balance, 2)
        })
        return True

    def exec_sell(close_price: float, reason: str) -> bool:
        nonlocal balance, position_units, entry_price, cash_out_at_entry, sl_price, tp_price
        if position_units <= 0:
            return False
        sell_px = float(close_price) * (1.0 - SLIPPAGE_BPS / 10_000.0)
        gross = position_units * sell_px
        fee = gross * FEE_RATE
        net = gross - fee
        balance += net
        realized_pnl = net - cash_out_at_entry

        trades.append({
            "action": "SELL",
            "price": round(sell_px, 8),
            "units": round(position_units, 12),
            "fee": round(float(fee), 6),
            "realized_pnl": round(float(realized_pnl), 6),
            "after_balance": round(balance, 2),
            "reason": reason
        })

        position_units = 0.0
        entry_price = None
        cash_out_at_entry = 0.0
        sl_price = None
        tp_price = None
        return True

    for i in range(1, len(df)):
        price = float(df["close"].iloc[i])

        # mark-to-market equity
        mark_eq = balance + (position_units * price if position_units > 0 else 0.0)
        equity_curve.append(float(mark_eq))

        # manage open position with SL/TP
        if position_units > 0:
            if price <= sl_price:
                exec_sell(price, reason="stop_loss")
                cooldown_until = i + COOLDOWN_BARS
                continue
            if price >= tp_price:
                exec_sell(price, reason="take_profit")
                continue

        # cooldown
        if i <= cooldown_until:
            continue

        # entries / exits
        if position_units == 0 and bool(df["entry_long"].iloc[i]):
            exec_buy(price, i)
            continue

        if position_units > 0 and bool(df["exit_signal"].iloc[i]):
            exec_sell(price, reason="exit_signal")
            continue

    # close at last bar
    if position_units > 0:
        exec_sell(float(df["close"].iloc[-1]), reason="end_bar")
        equity_curve.append(float(balance))

    # metrics
    if not equity_curve:
        equity_curve = [START_BALANCE]
    peak = equity_curve[0]
    max_dd = 0.0
    for eq in equity_curve:
        peak = max(peak, eq)
        dd = (peak - eq) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)

    sells = [t for t in trades if t["action"] == "SELL"]
    wins = [t for t in sells if t.get("realized_pnl", 0.0) > 0.0]
    win_rate = (len(wins) / len(sells) * 100.0) if sells else 0.0

    return {
        "final_balance": float(balance),
        "total_return_pct": (float(balance) / float(START_BALANCE) - 1.0) * 100.0,
        "num_trades": len(sells),
        "win_rate_pct": float(win_rate),
        "max_drawdown_pct": float(max_dd * 100.0),
        "trades": trades,
    }


# ---------- Main ----------
if __name__ == "__main__":
    # 1) Load base TF data
    df = fetch_data(symbol=SYMBOL, interval=INTERVAL, limit=LIMIT)
    df = df.sort_values("timestamp").reset_index(drop=True)

    # 2) Higher-TF filter + ATR
    df = add_htf_trend(df)
    df = add_atr(df, period=ATR_PERIOD)

    # 3) Build strategy signals
    if STRATEGY == "ema_crossover":
        df = build_signals_ema(df)
    elif STRATEGY == "rsi_mean_reversion":
        df = build_signals_rsi_mr(df)
    elif STRATEGY == "donchian_breakout":
        df = build_signals_donchian(df)
    else:
        raise ValueError(f"Unknown STRATEGY: {STRATEGY}")

    # 4) Backtest
    stats = backtest(df)

    # 5) Summary
    print(f"Strategy:     {STRATEGY}")
    print(f"Start balance:{START_BALANCE:.2f}")
    print(f"Final balance:{stats['final_balance']:.2f}")
    print(f"Total return: {stats['total_return_pct']:.2f}%")
    print(f"Trades:       {stats['num_trades']}")
    print(f"Win rate:     {stats['win_rate_pct']:.2f}%")
    print(f"Max drawdown: {stats['max_drawdown_pct']:.2f}%\n")

    print("Last 10 trades:")
    for t in stats["trades"][-10:]:
        print(t)

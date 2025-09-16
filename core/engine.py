# engine.py
import pandas as pd

# ===== Common Config Defaults (can be overridden by brain) =====
FEE_RATE = 0.001        # 0.10% per side
SLIPPAGE_BPS = 2        # 0.02% per side
ATR_PERIOD = 14
ATR_SL_MULT = 2.0
ATR_TP_MULT = 4.0
COOLDOWN_BARS = 2

# ===== Indicators =====
def add_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.DataFrame:
    prev_close = df["close"].shift(1)
    tr1 = (df["high"] - df["low"]).abs()
    tr2 = (df["high"] - prev_close).abs()
    tr3 = (df["low"] - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(window=period, min_periods=period).mean()
    return df

def add_htf_ema_flag(df_base: pd.DataFrame, htf_df: pd.DataFrame, ema_len: int = 200) -> pd.DataFrame:
    htf = htf_df.sort_values("timestamp").reset_index(drop=True).copy()
    htf["HTF_EMA"] = htf["close"].ewm(span=ema_len, adjust=False).mean()
    base = df_base.sort_values("timestamp").reset_index(drop=True).copy()
    merged = pd.merge_asof(
        base, htf[["timestamp", "HTF_EMA"]],
        on="timestamp", direction="backward"
    )
    merged["HTF_TREND_UP"] = merged["close"] > merged["HTF_EMA"]
    return merged

def add_adx(df, period=14):
    high, low, close = df["high"], df["low"], df["close"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = ((up_move > down_move) & (up_move > 0)) * up_move
    minus_dm = ((down_move > up_move) & (down_move > 0)) * down_move

    tr1 = (high - low).abs()
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr.replace(0, 1e-9))
    minus_di = 100 * (minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr.replace(0, 1e-9))
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, 1e-9)) * 100
    df["ADX"] = dx.ewm(alpha=1/period, adjust=False).mean()
    return df

# ===== Strategy Signal Builders =====
def build_ema_crossover(df: pd.DataFrame, ema_short=10, ema_long=50, confirm_bars=2,
                        min_gap_pct=0.25, require_htf=True, **_ignored) -> pd.DataFrame:
    df = df.copy()
    df["EMA_short"] = df["close"].ewm(span=ema_short, adjust=False).mean()
    df["EMA_long"]  = df["close"].ewm(span=ema_long,  adjust=False).mean()
    df["regime"] = 0
    df.loc[df["EMA_short"] > df["EMA_long"], "regime"] = 1
    df.loc[df["EMA_short"] < df["EMA_long"], "regime"] = -1

    df["entry_long"] = False
    df["exit_signal"] = False

    for i in range(len(df)):
        if i - confirm_bars < 1:
            continue
        # confirm long regime
        if all(df["regime"].iloc[j] == 1 for j in range(i - confirm_bars + 1, i + 1)) \
           and df["regime"].iloc[i - confirm_bars] == -1:
            s = float(df["EMA_short"].iloc[i])
            l = float(df["EMA_long"].iloc[i])
            if l != 0:
                gap_ok = (s - l) / l * 100.0 >= min_gap_pct
                htf_ok = bool(df.get("HTF_TREND_UP", pd.Series([True]*len(df))).iloc[i]) if require_htf else True
                if gap_ok and htf_ok:
                    df.at[i, "entry_long"] = True

        # confirm short regime (exit)
        if all(df["regime"].iloc[j] == -1 for j in range(i - confirm_bars + 1, i + 1)) \
           and df["regime"].iloc[i - confirm_bars] == 1:
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

def build_rsi_mean_reversion(df: pd.DataFrame, rsi_len=14, rsi_buy=30, rsi_exit=55,
                             require_htf=True, **_ignored) -> pd.DataFrame:
    df = df.copy()
    df["RSI"] = rsi(df["close"], rsi_len)
    up_ok = df.get("HTF_TREND_UP", pd.Series([True]*len(df)))
    df["entry_long"] = (df["RSI"] < rsi_buy) & (up_ok if require_htf else True)
    df["exit_signal"] = (df["RSI"] > rsi_exit)
    return df

def build_donchian_breakout(df: pd.DataFrame, entry_n=30, exit_n=12,
                             require_htf=True, adx_min=0, **_ignored) -> pd.DataFrame:
    df = df.copy()
    df["don_high"] = df["high"].rolling(entry_n).max().shift(1)
    df["don_low_exit"] = df["low"].rolling(exit_n).min().shift(1)

    up_ok = df.get("HTF_TREND_UP", pd.Series([True]*len(df)))
    df["entry_long"] = (df["close"] > df["don_high"]) & (up_ok if require_htf else True)
    df["exit_signal"] = (df["close"] < df["don_low_exit"])

    if adx_min and adx_min > 0:
        if "ADX" not in df.columns:
            df = add_adx(df, period=14)
        df["entry_long"] = df["entry_long"] & (df["ADX"] > adx_min)

    return df

# registry for the brain
STRATEGY_BUILDERS = {
    "ema_crossover": build_ema_crossover,
    "rsi_mean_reversion": build_rsi_mean_reversion,
    "donchian_breakout": build_donchian_breakout,
}

# ===== Backtest / Execution (long-only) =====
def backtest_long_only(
    df: pd.DataFrame,
    fraction_per_trade: float = 0.33,
    fee_rate: float = FEE_RATE,
    slippage_bps: int = SLIPPAGE_BPS,
    atr_sl_mult: float = ATR_SL_MULT,
    atr_tp_mult: float = ATR_TP_MULT,
    cooldown_bars: int = COOLDOWN_BARS,
) -> dict:
    balance = 100.0
    position_units = 0.0
    entry_price = None
    cash_out_entry = 0.0
    sl_price = None
    tp_price = None
    cooldown_until = -1

    trades = []
    equity_curve = []

    for i in range(1, len(df)):
        price = float(df["close"].iloc[i])
        atr_val = float(df["ATR"].iloc[i]) if pd.notna(df["ATR"].iloc[i]) and df["ATR"].iloc[i] > 0 else price * 0.002

        # mark to market
        mark_eq = balance + (position_units * price if position_units > 0 else 0.0)
        equity_curve.append(mark_eq)

        # manage open position
        if position_units > 0:
            if price <= sl_price:
                sell_px = price * (1.0 - slippage_bps / 10_000.0)
                gross = position_units * sell_px
                fee = gross * fee_rate
                net = gross - fee
                balance += net
                realized = net - cash_out_entry
                trades.append({"action": "SELL", "price": round(sell_px,8), "units": round(position_units,12),
                               "fee": round(fee,6), "realized_pnl": round(realized,6),
                               "after_balance": round(balance,2), "reason":"stop_loss"})
                position_units = 0.0; entry_price=None; cash_out_entry=0.0; sl_price=None; tp_price=None
                cooldown_until = i + cooldown_bars
                continue
            if price >= tp_price:
                sell_px = price * (1.0 - slippage_bps / 10_000.0)
                gross = position_units * sell_px
                fee = gross * fee_rate
                net = gross - fee
                balance += net
                realized = net - cash_out_entry
                trades.append({"action": "SELL", "price": round(sell_px,8), "units": round(position_units,12),
                               "fee": round(fee,6), "realized_pnl": round(realized,6),
                               "after_balance": round(balance,2), "reason":"take_profit"})
                position_units = 0.0; entry_price=None; cash_out_entry=0.0; sl_price=None; tp_price=None
                continue

        # cooldown
        if i <= cooldown_until:
            continue

        # signal exits (optional extra exit)
        if position_units > 0 and bool(df["exit_signal"].iloc[i]):
            sell_px = price * (1.0 - slippage_bps / 10_000.0)
            gross = position_units * sell_px
            fee = gross * fee_rate
            net = gross - fee
            balance += net
            realized = net - cash_out_entry
            trades.append({"action": "SELL", "price": round(sell_px,8), "units": round(position_units,12),
                           "fee": round(fee,6), "realized_pnl": round(realized,6),
                           "after_balance": round(balance,2), "reason":"exit_signal"})
            position_units = 0.0; entry_price=None; cash_out_entry=0.0; sl_price=None; tp_price=None
            continue

        # entries
        if position_units == 0 and bool(df["entry_long"].iloc[i]):
            buy_px = price * (1.0 + slippage_bps / 10_000.0)
            trade_cash = balance * fraction_per_trade
            if trade_cash <= 0: 
                continue
            units = trade_cash / buy_px
            if units <= 0: 
                continue
            gross = units * buy_px
            fee = gross * fee_rate
            total_out = gross + fee
            if total_out > balance:
                scale = balance / total_out
                units *= scale
                gross = units * buy_px
                fee = gross * fee_rate
                total_out = gross + fee
            if total_out <= 0 or units <= 0:
                continue
            balance -= total_out
            position_units = units
            entry_price = buy_px
            cash_out_entry = total_out
            sl_price = entry_price - atr_sl_mult * atr_val
            tp_price = entry_price + atr_tp_mult * atr_val
            trades.append({"action":"BUY","price": round(buy_px,8),"units": round(units,12),
                           "fee": round(fee,6),"after_balance": round(balance,2)})

    # close any open position at the end
    if position_units > 0:
        price = float(df["close"].iloc[-1])
        sell_px = price * (1.0 - SLIPPAGE_BPS / 10_000.0)
        gross = position_units * sell_px
        fee = gross * FEE_RATE
        net = gross - fee
        balance += net
        realized = net - cash_out_entry
        trades.append({"action":"SELL","price": round(sell_px,8),"units": round(position_units,12),
                       "fee": round(fee,6),"realized_pnl": round(realized,6),
                       "after_balance": round(balance,2), "reason":"end_bar"})

    # metrics
    if not equity_curve:
        equity_curve = [100.0]
    peak = equity_curve[0]; max_dd = 0.0
    for eq in equity_curve:
        peak = max(peak, eq)
        dd = (peak - eq) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)

    sells = [t for t in trades if t["action"] == "SELL"]
    wins  = [t for t in sells if t.get("realized_pnl", 0) > 0]
    win_rate = 100.0 * len(wins) / len(sells) if sells else 0.0
    total_return_pct = (balance / 100.0 - 1.0) * 100.0

    return {
        "final_balance": round(balance, 2),
        "total_return_pct": round(total_return_pct, 2),
        "num_trades": len(sells),
        "win_rate_pct": round(win_rate, 2),
        "max_drawdown_pct": round(max_dd * 100.0, 2),
        "trades": trades
    }

# ===== Convenience: build signals by name =====
def build_signals(df: pd.DataFrame, name: str, params: dict) -> pd.DataFrame:
    if name not in STRATEGY_BUILDERS:
        raise ValueError(f"Unknown strategy: {name}")
    return STRATEGY_BUILDERS[name](df.copy(), **params)

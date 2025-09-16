# evaluator.py
"""
Module for strategy evaluation including walk-forward selection, backtesting, and performance metrics.
Provides functions to backtest trading signals and select the best strategy segments over time.
"""

from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import numpy as np
import pandas as pd

from .indicators import adx
from .strategies import StrategyConfig, ma_x_signal, apply_regime_filter

import pandas as pd
from typing import Optional
from .strategy import walk_forward_select, WFSelParams, equity_curve

def last_signal_within(sig: pd.Series, bars: int):
    sig = sig.astype(int)
    if len(sig) == 0:
        return 0, 10**9
    last = int(sig.iloc[-1])
    changes = sig.ne(sig.shift()).to_numpy().nonzero()[0]
    if len(changes) == 0:
        return last, 10**9
    last_change_idx = changes[-1]
    age = len(sig) - 1 - last_change_idx
    return last, age

def last_entry_price(close: pd.Series, sig: pd.Series, side_now: int) -> Optional[float]:
    if side_now == 0 or len(sig) == 0:
        return None
    sig = sig.astype(int)
    for i in range(len(sig)-1, 0, -1):
        if sig.iat[i] == side_now and sig.iat[i-1] == 0:
            return float(close.iat[i])
        if sig.iat[i] == 0:
            break
    return None

@dataclass
class WFSelParams:
    """Parameters for walk-forward selection window sizes and thresholds."""
    train: int          # number of bars in training window
    test: int           # number of bars in testing (validation) window
    step: int           # step size to slide the window
    min_trades: int     # minimum number of trades in training to consider strategy
    min_expectancy: float  # minimum average trade return in training to consider strategy
    min_sharpe: float   # minimum Sharpe ratio in testing to accept strategy
    adx_threshold: float  # ADX threshold to consider a trending regime
    adx_len: int        # period for ADX calculation
    allow_long: bool    # whether long positions are allowed
    allow_short: bool   # whether short positions are allowed

def equity_curve(close: pd.Series, sig: pd.Series, fee: float = 0.0004, slip_bps: float = 1.0) -> Tuple[pd.Series, Dict[str, float]]:
    """
    Compute the equity curve for a strategy's signals (sig) applied to the close price series.
    Assumes positions are entered/exited at close prices with specified trading costs.
    Returns a tuple of (equity_series, metrics_dict).
    Metrics include total trades, expectancy (average return per trade), win_rate, Sharpe ratio, and total_return.
    """
    px = close.astype(float)
    # Compute per-bar returns
    ret = px.pct_change().fillna(0.0)
    # Position on each bar (hold previous bar's signal)
    pos = sig.shift(1).fillna(0).astype(int)
    # Identify where position changes (entries/exits)
    pos_change = (pos != pos.shift(1)).fillna(False).astype(int)
    # Trading cost per position change (fee + slippage)
    trade_cost = pos_change * (fee + slip_bps / 10_000.0)
    # Strategy returns with costs accounted for
    strat_ret = (ret * pos) - trade_cost
    # Cumulative equity assuming starting equity of 1.0
    equity = (1.0 + strat_ret).cumprod()

    # Calculate performance metrics
    entries = ((pos != 0) & (pos != pos.shift(1))).sum()  # count of entries into a position
    trades = int(entries)
    if trades == 0:
        sharpe = 0.0
        expectancy = 0.0
        win_rate = 0.0
    else:
        # Compute per-trade P&L by accumulating returns during each trade
        trade_pnls: List[float] = []
        in_trade = False
        acc_return = 0.0
        for i in range(1, len(strat_ret)):
            if not in_trade and pos.iloc[i] != 0 and pos.iloc[i] != pos.iloc[i - 1]:
                # Starting a new trade
                in_trade = True
                acc_return = 0.0
            if in_trade:
                acc_return += float(strat_ret.iloc[i])
                # Check if trade ends at next step (position goes to 0 or flips)
                next_same = (i + 1 < len(pos)) and (pos.iloc[i + 1] == pos.iloc[i])
                if pos.iloc[i] == 0 or not next_same:
                    # Trade closed (either went flat or position direction changed on next bar)
                    trade_pnls.append(acc_return)
                    in_trade = False
        if len(trade_pnls) == 0:
            trade_pnls = [0.0]
        trade_pnls_np = np.array(trade_pnls, dtype=float)
        expectancy = float(np.mean(trade_pnls_np))
        win_rate = float((trade_pnls_np > 0).mean()) if len(trade_pnls_np) > 0 else 0.0
        # Sharpe ratio (based on strategy returns series)
        strat_std = float(np.std(strat_ret))
        sharpe = float(np.mean(strat_ret) / (strat_std + 1e-12)) if strat_std > 1e-12 else 0.0

    metrics = {
        "trades": trades,
        "expectancy": float(expectancy),
        "win_rate": float(win_rate),
        "sharpe": float(sharpe),
        "total_return": float(equity.iloc[-1] - 1.0) if len(equity) > 0 else 0.0,
    }
    return equity, metrics

def walk_forward_select(df: pd.DataFrame, sel: WFSelParams, fee: float, slip_bps: float, strategies: List[StrategyConfig]) -> List[Dict]:
    """
    Perform walk-forward selection over the dataframe `df`.
    Splits the data into sequential train/test segments and finds the best strategy (from `strategies`) for each segment.
    Returns a list of segment dictionaries, each containing the chosen strategy and performance metrics for that segment.
    """
    close = df["close"]
    # Calculate ADX once for the whole dataset for efficiency (used in regime filtering)
    adx_series = adx(df["high"], df["low"], df["close"], sel.adx_len)
    segments: List[Dict] = []
    N = len(df)
    if N < (sel.train + sel.test + 10):
        # Not enough data for even one segment
        return segments

    # Slide the window in increments of sel.step
    for start in range(0, N - (sel.train + sel.test), sel.step):
        tr_a = start
        tr_b = start + sel.train
        te_a = tr_b
        te_b = tr_b + sel.test
        # Initialize segment info
        segment_info = {
            "start": df.index[tr_a],
            "end": df.index[te_b - 1] if te_b - 1 < len(df.index) else df.index[-1],
            "regime": "trend",
            "strategy": None,
            "params": None,
            "exp_train": np.nan,
            "n_train": np.nan,
            "exp_test": np.nan,
            "n_test": np.nan,
            "sharpe_test": np.nan,
        }
        best_choice = None  # track best strategy (score, name, params, train_metrics, test_metrics)
        # Evaluate each candidate strategy on the training window
        for sc in strategies:
            if sc.name == "MA_X":  # Moving Average Crossover strategy
                fast = sc.params.get("fast", 13)
                slow = sc.params.get("slow", 34)
                if fast >= slow:
                    continue  # skip invalid parameter sets
                # Generate signals for full data (so that indicators are warmed up properly)
                raw_sig = ma_x_signal(close, fast, slow)
                filt_sig = apply_regime_filter(raw_sig, adx_series, sel.adx_threshold, sel.allow_long, sel.allow_short)
                # Backtest on training segment
                _, train_metrics = equity_curve(close.iloc[tr_a:tr_b], filt_sig.iloc[tr_a:tr_b], fee=fee, slip_bps=slip_bps)
                if train_metrics["trades"] < sel.min_trades or train_metrics["expectancy"] < sel.min_expectancy:
                    # Skip this strategy if it doesn't meet minimum requirements in training
                    continue
                # Scoring: combination of Sharpe and expectancy (weighted)
                score = (train_metrics["sharpe"] * 1.0) + (train_metrics["expectancy"] * 10.0)
                if best_choice is None or score > best_choice[0]:
                    # Evaluate on test segment for the current best
                    _, test_metrics = equity_curve(close.iloc[te_a:te_b], filt_sig.iloc[te_a:te_b], fee=fee, slip_bps=slip_bps)
                    best_choice = (score, sc.name, {"fast": fast, "slow": slow}, train_metrics, test_metrics)
            # Additional strategies can be added here with elif blocks or dynamic dispatch

        if best_choice is None:
            # No strategy qualified for this segment
            segments.append(segment_info)
            continue

        # Unpack best strategy choice for this segment
        _, strat_name, strat_params, train_metrics, test_metrics = best_choice
        # Validate test performance against minimum criteria
        if test_metrics["trades"] < max(1, int(sel.min_trades * 0.5)) or test_metrics["sharpe"] < sel.min_sharpe:
            # Disqualify if not enough trades in test or Sharpe below threshold
            segments.append(segment_info)
            continue

        # Fill segment information with chosen strategy details and metrics
        segment_info.update({
            "strategy": strat_name,
            "params": strat_params,
            "exp_train": train_metrics.get("expectancy", np.nan),
            "n_train": train_metrics.get("trades", np.nan),
            "exp_test": test_metrics.get("expectancy", np.nan),
            "n_test": test_metrics.get("trades", np.nan),
            "sharpe_test": test_metrics.get("sharpe", np.nan),
        })
        segments.append(segment_info)
    return segments

def last_signal_within(sig: pd.Series, bars: int) -> Tuple[int, int]:
    """
    Check the signal series for the most recent non-zero signal within the last `bars` bars.
    Returns a tuple (signal_value, age) where signal_value is the last non-zero signal (+1 or -1, or 0 if none) and age is how many bars ago it occurred.
    If no signal in the window, returns (0, large_number).
    Note: age=0 means the last bar itself has a non-zero signal.
    """
    if bars < 1:
        bars = 1
    window = sig.iloc[-max(2, bars + 1):]  # consider at least 2 bars for comparison
    recent_signals = window[window != 0]
    if recent_signals.empty:
        # No non-zero signals in the recent window
        return 0, 10000
    last_idx = recent_signals.index[-1]
    # Determine index position of last signal in the original series
    pos_last = sig.index.get_loc(last_idx)
    if isinstance(pos_last, slice):
        pos_last = pos_last.start  # get integer position if a slice is returned
    age_bars = len(sig) - 1 - pos_last
    last_signal_value = int(recent_signals.iloc[-1])
    return last_signal_value, int(age_bars)

def last_entry_price(close: pd.Series, sig: pd.Series, side: int) -> Optional[float]:
    """
    Get the close price at which the last entry into `side` (1 for long, -1 for short) occurred.
    If there is no such entry in the signal history, returns None.
    """
    if side == 0:
        return None
    # Find points where the signal flips into the specified side
    flips = (sig != sig.shift(1)).fillna(False)
    entry_points = sig[(sig == side) & flips].index
    if len(entry_points) == 0:
        return None
    last_entry_idx = entry_points[-1]
    # Return the closing price at the last entry index
    price_value = close.loc[last_entry_idx]
    return float(price_value)

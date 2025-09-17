# bot/brain.py
# Aethelred Brain â€” walk-forward regime selection, optional ML gating,
# paper ledger + metrics output for the dashboard.
#
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# SECTION INDEX (use your editor's search with:  # [Sx]  ):
# [S1] Imports & small utilities
# [S2] Strategy parameter helpers & regime helpers
# [S3] PnL & metrics (bar level + trade level)
# [S4] Walk-forward selection (folds + best strategy per regime)
# [S5] Paper state, ATR sizing & ledger
# [S6] CSV helpers
# [S7] Auto-tune (windows & ADX)
# [S8] CLI (parse_args)
# [S9] main() â€” ties everything together
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

from __future__ import annotations

# [S1] â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Imports & small utilities

import argparse
import json
import math
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Local modules (keep names stable so other files continue to work)
from bot.exchange import fetch_ohlcv_paginated
from bot.strategy import (
    moving_average_crossover,  # "ma"
    donchian_signal,           # "donchian"
    rsi_mr_signal,             # "rsi_mr"
    adx,                       # ADX filter for regime
)
from bot.autoparams import suggest_params_from_df, persist_params, load_persisted
from bot.ml import train_save_model, predict_last_proba
from bot.ml import ml_model_path
from bot.ml import ml_model_path`r`n
from bot.ml import ml_model_path

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slip_from_bps(bps: float | None) -> float:
    return 0.0 if bps is None else float(bps) / 10_000.0


def _pct_change(series: pd.Series) -> pd.Series:
    return series.pct_change().replace([np.inf, -np.inf], 0.0).fillna(0.0)


def _bars_per_year(interval: str) -> float:
    """Rough bars-per-year given a timeframe string like 15m/1h/4h/1d."""
    iv = interval.strip().lower()
    num = "".join(ch for ch in iv if ch.isdigit())
    unit = "".join(ch for ch in iv if ch.isalpha())
    n = float(num) if num else 1.0
    if unit == "m":
        minutes = n
    elif unit == "h":
        minutes = n * 60.0
    elif unit in ("d", "day"):
        minutes = n * 60.0 * 24.0
    else:
        minutes = n * 60.0  # fallback: hours
    return (365.0 * 24.0 * 60.0) / max(1.0, minutes)


def _ann_factor(interval: str) -> float:
    return math.sqrt(_bars_per_year(interval))


def _safe_float(x: Any) -> Optional[float]:
    try:
        v = float(x)
        return None if (math.isnan(v) or math.isinf(v)) else v
    except Exception:
        return None


def sanitize(obj: Any) -> Any:
    """Recursively NaN/Inf-safe for JSON."""
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    if isinstance(obj, float):
        return _safe_float(obj)
    return obj


# [S2] â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Strategy parameter helpers & regime helpers
# (These helpers keep params in one place and are used both in selection and live)

def _donchian_n(tf: str) -> int:
    return {"1m": 40, "5m": 50, "15m": 70, "1h": 80, "4h": 100, "1d": 150}.get(tf, 80)


def _rsi_params(tf: str) -> Tuple[int, int, int]:
    # (length, oversold, overbought)
    table = {
        "1m": (7, 20, 80), "5m": (8, 25, 75), "15m": (9, 30, 70),
        "1h": (10, 30, 70), "4h": (14, 30, 70), "1d": (14, 30, 70),
    }
    return table.get(tf, (14, 30, 70))


def _ma_params(tf: str) -> Tuple[int, int]:
    # (fast, slow)
    table = {
        "1m": (12, 26), "5m": (20, 50), "15m": (24, 60),
        "1h": (24, 72), "4h": (20, 100), "1d": (50, 200),
    }
    return table.get(tf, (20, 50))


def _regime_from_adx(df: pd.DataFrame, adx_len: int, threshold: float) -> str:
    """Return 'trend' or 'chop' from ADX."""
    try:
        val = float(adx(df["high"], df["low"], df["close"], adx_len).iloc[-1])
    except Exception:
        val = 0.0
    return "trend" if val >= threshold else "chop"


def _candles_per_day(interval: str) -> int:
    m = {"1m": 1440, "3m": 480, "5m": 288, "15m": 96, "30m": 48,
         "1h": 24, "2h": 12, "4h": 6, "6h": 4, "12h": 2, "1d": 1}
    return m.get(interval, 24)


def _default_ml_model_path(symbol: str, interval: str) -> Path:
    return Path("ml_models") / f"{symbol.replace('/', '_')}_{interval}_lin.pkl"


# [S3] â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# PnL & metrics (bar level + trade level)
# (Used by both walk-forward selection and live reporting)

def _apply_fee_slip(r: pd.Series, fee_rate: float, slip_rate: float, flips: pd.Series) -> pd.Series:
    cost = (fee_rate + slip_rate)
    return r - flips.astype(float) * cost


def pnl_from_signal(close: pd.Series, signal: pd.Series,
                    fee_rate: float, slip_rate: float) -> Tuple[pd.Series, pd.Series]:
    sig = signal.fillna(0).astype(int)
    pos = sig.shift(1).fillna(0).astype(float)        # position is yesterday's signal
    ret_raw = _pct_change(close) * pos
    flips = pos.diff().ne(0).fillna(False)
    ret_net = _apply_fee_slip(ret_raw, fee_rate, slip_rate, flips)
    return ret_net, pos


def _parse_trades(sig_series: pd.Series, asset_ret: pd.Series) -> Tuple[int, float, float]:
    """Crude trade parser: accumulate returns while in a position; close when flat."""
    s = sig_series.fillna(0).astype(int).values
    r = asset_ret.fillna(0.0).values
    in_pos = False
    pos = 0
    acc = 0.0
    trades: List[float] = []
    for si, ri in zip(s, r):
        if not in_pos and si != 0:
            in_pos = True
            pos = si
            acc = 0.0
        if in_pos:
            acc += ri * pos
            if si == 0:
                trades.append(acc)
                in_pos = False
                pos = 0
                acc = 0.0
    n = len(trades)
    if n == 0:
        return 0, 0.0, 0.0
    wins = [x for x in trades if x > 0]
    losses = [-x for x in trades if x < 0]
    win_rate = len(wins) / n
    pf = (sum(wins) / sum(losses)) if len(losses) > 0 else (float("inf") if len(wins) > 0 else 0.0)
    return n, float(win_rate), float(pf)


def compute_metrics(interval: str,
                    ret_net_full: pd.Series,
                    pos_full: pd.Series,
                    close_series: Optional[pd.Series],
                    lookback: int = 1000) -> Dict[str, Any]:
    """Summary metrics for the last `lookback` bars."""
    r = pd.Series(ret_net_full).replace([np.inf, -np.inf], 0.0).fillna(0.0).tail(lookback)
    p = pd.Series(pos_full).fillna(0.0).tail(lookback)
    if r.empty:
        return {
            "bars_used": 0, "ann_return": 0.0, "ann_vol": 0.0, "sharpe_ann": 0.0,
            "max_drawdown": 0.0, "win_rate_bar": 0.0, "profit_factor_bar": 0.0,
            "trade_count": 0, "avg_bar_return": 0.0,
        }

    # Equity / drawdown
    eq = (1.0 + r).cumprod()
    peak = eq.cummax()
    dd = (eq / peak - 1.0)
    max_dd = float(dd.min()) if not dd.empty else 0.0

    # Annualized bar stats
    bpy = _bars_per_year(interval)
    mu = float(r.mean())
    vol = float(r.std(ddof=0))
    ann_return = float((1.0 + mu) ** bpy - 1.0)          # geometric approx
    ann_vol = float(vol * math.sqrt(bpy)) if vol > 0 else 0.0
    sharpe_ann = float(_ann_factor(interval) * mu / (vol + 1e-9)) if vol > 0 else 0.0

    # In-position "bar win rate" & bar PF (for the mini chart on the dashboard)
    mask = (p != 0)
    inpos = r[mask]
    wins = inpos[inpos > 0].sum()
    losses = -inpos[inpos < 0].sum()
    win_rate_bar = float((inpos > 0).mean()) if len(inpos) else 0.0
    profit_factor_bar = (wins / losses) if losses > 0 else (float("inf") if wins > 0 else 0.0)

    # Trade-level metrics (parse from signal-like series)
    if close_series is not None and len(close_series) >= len(r):
        asset_ret = _pct_change(close_series.tail(len(r)))
    else:
        asset_ret = r
    sig_like = p.shift(-1).fillna(0.0).round().astype(int)  # reverse of pos = sig.shift(1)
    n_trades, win_rate_trade, profit_factor_trade = _parse_trades(sig_like, asset_ret)

    return {
        "bars_used": int(len(r)),
        "ann_return": ann_return,
        "ann_vol": ann_vol,
        "sharpe_ann": sharpe_ann,
        "max_drawdown": max_dd,
        "win_rate_bar": win_rate_bar,
        "profit_factor_bar": float(profit_factor_bar),
        "trade_count": int(n_trades),
        "avg_bar_return": mu,
        "win_rate_trade": float(win_rate_trade),
        "profit_factor_trade": float(profit_factor_trade),
    }


# [S4] â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Walk-forward selection (folds + best strategy per regime)
# (Feeds: [S3] metrics, Uses: [S2] params, Returns: chosen name + folds)

@dataclass
class FoldResult:
    start: int
    end: int
    regime: str
    strategy: Optional[str]
    exp_train: float
    n_train: int
    exp_test: float
    n_test: int
    sharpe_test: float


def _window_grid(N: int, min_folds: int = 3) -> List[Tuple[int, int, int]]:
    """Broad, reasonable grid that fits at least `min_folds` folds."""
    if N < 200:
        return [(int(N * 0.6), int(N * 0.3), max(1, int(N * 0.15)))]
    grid: List[Tuple[int, int, int]] = []
    for tf in (0.15, 0.20, 0.25, 0.30):
        test = max(80, int(N * tf))
        for tr_mul in (2.0, 2.5, 3.0):
            train = max(200, int(test * tr_mul))
            for step_frac in (0.4, 0.5, 0.6):
                step = max(40, int(test * step_frac))
                total = train + test
                if total + step > N:
                    continue
                folds = 1 + (N - total) // step
                if folds >= min_folds:
                    grid.append((train, test, step))
    # prefer more folds, then more train
    def score(t):
        train, test, step = t
        folds = 1 + (N - (train + test)) // step
        return (folds, train, test)
    grid.sort(key=score, reverse=True)
    return grid or [(int(N * 0.6), int(N * 0.3), max(1, int(N * 0.15)))]


def walk_forward_select(
    df: pd.DataFrame,
    timeframe: str,
    wf_train: int,
    wf_test: int,
    wf_step: int,
    adx_len: int,
    adx_threshold: float,
    allow_long: bool,
    allow_short: bool,
    fee_rate: float,
    slip_rate: float,
    min_trades: int = 10,
) -> Tuple[str, List[FoldResult]]:
    close, high, low = df["close"], df["high"], df["low"]

    # Pre-compute signals once
    ffast, fslow = _ma_params(timeframe)
    dn = _donchian_n(timeframe)
    rsi_len, rsi_lo, rsi_hi = _rsi_params(timeframe)

    sig_ma = moving_average_crossover(close, fast=ffast, slow=fslow,
                                      allow_long=allow_long, allow_short=allow_short)
    sig_don = donchian_signal(high, low, close, n=dn,
                              allow_long=allow_long, allow_short=allow_short)
    sig_rsi = rsi_mr_signal(close, rsi_len=rsi_len, os=rsi_lo, ob=rsi_hi,
                            allow_long=allow_long, allow_short=allow_short)

    folds: List[FoldResult] = []
    n = len(df)
    chosen = "none"

    i = 0
    while i + wf_train + wf_test <= n:
        tr_start = i
        tr_end = i + wf_train
        te_end = tr_end + wf_test

        df_tr = df.iloc[tr_start:tr_end]
        regime_tr = _regime_from_adx(df_tr, adx_len, adx_threshold)

        candidates: Dict[str, pd.Series] = (
            {"ma": sig_ma, "donchian": sig_don} if regime_tr == "trend" else {"rsi_mr": sig_rsi}
        )

        best_name = None
        best_sharpe = -1e9
        exp_train = float("nan")
        exp_test = float("nan")
        n_train = 0
        n_test = 0

        for name, sig in candidates.items():
            sig_tr = sig.iloc[tr_start:tr_end]
            sig_te = sig.iloc[tr_end:te_end]

            r_tr, _ = pnl_from_signal(close.iloc[tr_start:tr_end], sig_tr, fee_rate, slip_rate)
            r_te, _ = pnl_from_signal(close.iloc[tr_end:te_end],   sig_te, fee_rate, slip_rate)

            n_tr = int(np.abs(sig_tr.diff()).fillna(0).sum())
            n_te = int(np.abs(sig_te.diff()).fillna(0).sum())
            if n_tr < min_trades:
                continue

            exp_tr = float(r_tr.sum() / max(1, n_tr))
            exp_te = float(r_te.sum() / max(1, n_te))
            sharpe_te = float(_ann_factor(timeframe) * r_te.mean() / (r_te.std(ddof=0) + 1e-9)) if len(r_te) else 0.0

            if sharpe_te > best_sharpe:
                best_sharpe = sharpe_te
                best_name = name
                exp_train = exp_tr
                exp_test = exp_te
                n_train = n_tr
                n_test = n_te

        folds.append(FoldResult(
            start=tr_start + 1,
            end=te_end,
            regime=regime_tr,
            strategy=best_name,
            exp_train=float(exp_train if not math.isnan(exp_train) else 0.0),
            n_train=int(n_train),
            exp_test=float(exp_test if not math.isnan(exp_test) else 0.0),
            n_test=int(n_test),
            sharpe_test=float(best_sharpe if best_name else 0.0),
        ))

        if best_name:
            chosen = best_name

        i += wf_step

    return chosen, folds


# [S5] â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Paper state, ATR sizing & ledger
# (Used only in live run; independent of selection)

@dataclass
class PaperState:
    equity: float = 1000.0
    last_update: Optional[str] = None
    daily_drop_limit: float = 0.12
    day_start_equity: Optional[float] = None

    @classmethod
    def load(cls, p: Path) -> "PaperState":
        if not p.exists():
            return cls()
        data = json.loads(p.read_text(encoding="utf-8"))
        return cls(
            equity=float(data.get("equity", 1000.0)),
            last_update=data.get("last_update"),
            daily_drop_limit=float(data.get("daily_drop_limit", 0.12)),
            day_start_equity=(float(data["day_start_equity"]) if data.get("day_start_equity") is not None else None),
        )

    def save(self, p: Path) -> None:
        p.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    def reset_day_if_needed(self) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        last = (self.last_update or "")[:10]
        if last != today:
            self.day_start_equity = self.equity

    def circuit_tripped(self) -> bool:
        if self.day_start_equity is None:
            return False
        drop = (self.day_start_equity - self.equity) / max(1e-9, self.day_start_equity)
        return drop >= self.daily_drop_limit


def atr_from_hlc(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False).mean()


def position_size_from_atr(
    high: pd.Series, low: pd.Series, close: pd.Series,
    atr_len: int, risk_per_trade: float, max_pos: float
) -> float:
    atr_val = float(atr_from_hlc(high, low, close, atr_len).iloc[-1])
    px = float(close.iloc[-1])
    atr_pct = atr_val / max(1e-12, px)
    if atr_pct <= 0 or math.isnan(atr_pct) or math.isinf(atr_pct):
        return 0.0
    frac = risk_per_trade / atr_pct
    return float(max(0.0, min(max_pos, frac)))


def append_paper_ledger(ledger_path: Path, ts: str, symbol: str, signal: str, price: float,
                        ret_est: float, equity_before: float, equity_after: float, pos_frac: float) -> None:
    header = "ts,symbol,signal,price,ret_est,pos_frac,equity_before,equity_after\n"
    line = f"{ts},{symbol},{signal},{price:.8f},{ret_est:.8f},{pos_frac:.4f},{equity_before:.2f},{equity_after:.2f}\n"
    new = not ledger_path.exists()
    with ledger_path.open("a", encoding="utf-8") as f:
        if new:
            f.write(header)
        f.write(line)


# [S6] â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# CSV helpers
# (Shared by API/dashboard; keeps CSV schema stable)

def _metrics_path_from_signal(signal_path: Path, explicit: Optional[str]) -> Path:
    if explicit:
        return Path(explicit)
    name = signal_path.name
    if name.endswith("_signal.json"):
        return signal_path.with_name(name.replace("_signal.json", "_metrics.csv"))
    return signal_path.with_suffix(".metrics.csv")


def append_metrics_csv(path: Path, payload: Dict[str, Any]) -> None:
    header = [
        "ts","exchange","symbol","interval","strategy","signal","price",
        "bars_used","ann_return","ann_vol","sharpe_ann","max_drawdown",
        "win_rate_bar","profit_factor_bar","trade_count","avg_bar_return","paper_equity"
    ]
    new = not path.exists()
    row = [str(payload.get(k, "")) for k in header]
    with path.open("a", encoding="utf-8") as f:
        if new:
            f.write(",".join(header) + "\n")
        f.write(",".join(row) + "\n")


# [S7] â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Auto-tune (windows & ADX)
# (Very lightweight; gives healthy fold counts without deep grid-search)

def _pick_reasonable_adx(interval: str) -> Tuple[int, int]:
    cpd = _candles_per_day(interval)
    if cpd >= 288:     # <= 5m
        return 20, 14
    elif cpd >= 96:    # 15â€“30m
        return 18, 14
    elif cpd >= 24:    # 1h
        return 15, 14
    else:              # 4h+
        return 12, 14


def auto_tune(df: pd.DataFrame, interval: str, min_folds: int = 3) -> Dict[str, Any]:
    N = len(df)
    best = {"score": float("-inf")}
    for tr, te, st in _window_grid(N, min_folds=min_folds):
        total = tr + te
        folds = 1 + (N - total) // st
        # prefer â‰ˆ5 folds and larger train
        score = folds - 0.1 * abs(folds - 5) + 1e-6 * tr
        if score > best["score"]:
            best = {"score": score, "train": tr, "test": te, "step": st}
    th, ln = _pick_reasonable_adx(interval)
    best["adx_trend_threshold"] = th
    best["adx_len"] = ln
    return best


# [S8] â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# CLI (parse_args)
# (All knobs in one place; main() reads this once)

def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser("Aethelred Brain")

    ap.add_argument("--exchange", default="binance")
    ap.add_argument("--symbol",   default="BTC/USDT")
    ap.add_argument("--interval", default="4h")
    ap.add_argument("--limit",    default=5000, type=int)
    ap.add_argument("--profile",  default="easy")

    # walk-forward
    ap.add_argument("--wf-train", default=1000, type=int)
    ap.add_argument("--wf-test",  default=500,  type=int)
    ap.add_argument("--wf-step",  default=400,  type=int)

    ap.add_argument("--min-trades",     default=10,   type=int)
    ap.add_argument("--min-expectancy", default=0.0,  type=float)  # reserved
    ap.add_argument("--min-sharpe",     default=0.0,  type=float)  # reserved

    # regime
    ap.add_argument("--adx-trend-threshold", default=15.0, type=float)
    ap.add_argument("--adx-len",             default=14,   type=int)

    # direction
    ap.add_argument("--trend-long",     action="store_true", help="enable long signals")
    ap.add_argument("--trend-no-short", action="store_true", help="disable shorts")

    # costs / sizing
    ap.add_argument("--risk",     default=0.02,   type=float)
    ap.add_argument("--fee",      default=0.0004, type=float)
    ap.add_argument("--slip-bps", default=1.0,    type=float)
    ap.add_argument("--atr-len",  default=14,     type=int)
    ap.add_argument("--max-pos",  default=1.0,    type=float)

    # outputs / debug
    ap.add_argument("--emit-json",      action="store_true")
    ap.add_argument("--emit-json-file", default="brain_signal.json")
    ap.add_argument("--debug-segments", action="store_true")

    # paper trading
    ap.add_argument("--paper-ledger",     action="store_true")
    ap.add_argument("--paper-file",       default="brain_ledger.csv")
    ap.add_argument("--paper-state-file", default="brain_state.json")
    ap.add_argument("--paper-fee-bps",    default=None, type=float)
    ap.add_argument("--paper-slip-bps",   default=None, type=float)

    # misc
    ap.add_argument("--entry-age", default=6, type=int)

    # metrics
    ap.add_argument("--metrics-lookback", default=1000, type=int)
    ap.add_argument("--metrics-file",     default=None)

    # auto-tune WF & ADX
    ap.add_argument("--auto-tune",      action="store_true", help="Auto-tune WF windows/ADX each run")
    ap.add_argument("--min-folds",      type=int, default=3, help="Minimum WF folds with auto-tune")
    ap.add_argument("--tune-adx-grid",  type=str, default="10,15,20,25", help="ADX thresholds to try (comma-separated)")
    ap.add_argument("--tune-adx-lens",  type=str, default="10,14,20",    help="ADX lengths to try (comma-separated)")

    # selection guard
    ap.add_argument("--min-sharpe-select", type=float, default=0.20,
                    help="Minimum OOS Sharpe required to accept a WF selection")
    ap.add_argument("--no-require-pos-expectancy", action="store_true",
                    help="Allow selection even if best OOS expectancy â‰¤ 0")

    # optional regime/persist
    ap.add_argument("--auto-regime",          action="store_true",
                    help="Adapt WF windows and ADX thresholds from current regime")
    ap.add_argument("--persist-params",       action="store_true",
                    help="Save chosen settings/strategy to params_{symbol}_{interval}.json")
    ap.add_argument("--use-persisted-params", action="store_true",
                    help="Load params_{symbol}_{interval}.json if present and override windows/filters")

    # ML
    ap.add_argument("--ml-train",       action="store_true",
                    help="Train & save the ML model for this symbol/interval, then exit.")
    ap.add_argument("--ml-enable",      action="store_true",
                    help="Enable ML gate (load model if present and adjust signal).")
    ap.add_argument("--ml-horizon",     type=int,   default=1,
                    help="Prediction horizon in bars (e.g., 1 = next bar).")
    ap.add_argument("--ml-model-file",  type=str,   default=None,
                    help="Path to save/load ML model. Default: ml_models/{symbol}_{interval}_lin.pkl")
    ap.add_argument("--ml-threshold",   type=float, default=0.55,
                    help="Prob. threshold for LONG; (1-threshold) is used to veto LONG to FLAT.")

    return ap.parse_args()


# [S9] â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# main() â€” ties everything together
# Flow:
#   1) Fetch data
#   2) (optional) auto-tune / load persisted params / regime-adapt
#   3) Walk-forward selection + selection guard
#   4) Build live signal; (optional) ML gate
#   5) Paper trading & ledger
#   6) Emit JSON + metrics CSV

def main() -> None:
    t0 = time.perf_counter()
    args = parse_args()

    # allow UI overrides
    try:
        s = json.loads(Path("runtime_settings.json").read_text("utf-8"))
        args.risk = float(s.get("risk", args.risk))
        args.max_pos = float(s.get("max_pos", args.max_pos))
        if bool(s.get("no_short", True)):
            args.trend_no_short = True
        # optional circuit breaker flag available in your PaperState
    except Exception:
        pass


    # Direction
    allow_long = True if args.trend_long else True     # longs allowed by default
    allow_short = not args.trend_no_short

    fee_rate = float(args.fee)
    slip_rate = _slip_from_bps(args.slip_bps)

    # â”€â”€ data
    df = fetch_ohlcv_paginated(args.exchange, args.symbol, args.interval, args.limit)
    if df.empty or len(df) < 50:
        raise RuntimeError("Insufficient OHLCV data. Check symbol/timeframe or increase --limit.")

    # â”€â”€ ML training-only mode
    if args.ml_train:
        out_path = Path(args.ml_model_file) if args.ml_model_file else _default_ml_model_path(args.symbol, args.interval)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        train_save_model(df, horizon=args.ml_horizon, model_path=out_path)
        print(f"[ML] Trained & saved model to: {out_path}")
        return

    # â”€â”€ windows / adx defaults
    wf_train, wf_test, wf_step = args.wf_train, args.wf_test, args.wf_step
    adx_th, adx_len = args.adx_trend_threshold, args.adx_len
    auto_tuned = False

    # â”€â”€ optionally load persisted params first
    if args.use_persisted_params:
        loaded = load_persisted(args.symbol, args.interval)
        if loaded:
            wf_train = int(loaded.get("wf_train", wf_train))
            wf_test  = int(loaded.get("wf_test", wf_test))
            wf_step  = int(loaded.get("wf_step", wf_step))
            adx_th   = float(loaded.get("adx_trend_threshold", adx_th))
            adx_len  = int(loaded.get("adx_len", adx_len))

    # â”€â”€ adaptive windows if requested windows don't fit data
    req_total = wf_train + wf_test + 10
    if len(df) < req_total:
        total = max(50, len(df) - 10)
        wf_train = max(100, int(total * 0.65))
        wf_test  = max(50,  int(total * 0.25))
        wf_step  = max(25,  int(wf_test * 0.5))
        print(f"[WARN] Not enough data for requested WF windows "
              f"({len(df)} < {req_total}). Using adaptive windows: "
              f"train={wf_train}, test={wf_test}, step={wf_step}.")

    # â”€â”€ optional: auto-tune (lightweight heuristic)
    if args.auto_tune:
        tuned = auto_tune(df, args.interval, min_folds=args.min_folds)
        wf_train, wf_test, wf_step = tuned["train"], tuned["test"], tuned["step"]
        adx_th, adx_len = tuned["adx_trend_threshold"], tuned["adx_len"]
        auto_tuned = True

    # â”€â”€ optional: regime-adaptive params
    if args.auto_regime:
        sug = suggest_params_from_df(df, args.interval)
        wf_train = int(sug.get("wf_train", wf_train))
        wf_test  = int(sug.get("wf_test",  wf_test))
        wf_step  = int(sug.get("wf_step",  wf_step))
        adx_th   = float(sug.get("adx_trend_threshold", adx_th))
        adx_len  = int(sug.get("adx_len", adx_len))

    # â”€â”€ WF selection
    chosen, folds = walk_forward_select(
        df=df,
        timeframe=args.interval,
        wf_train=wf_train,
        wf_test=wf_test,
        wf_step=wf_step,
        adx_len=adx_len,
        adx_threshold=adx_th,
        allow_long=allow_long,
        allow_short=allow_short,
        fee_rate=fee_rate,
        slip_rate=slip_rate,
        min_trades=args.min_trades,
    )

    # â”€â”€ Selection guard: ensure OOS quality before taking the live signal
    MIN_OOS_SHARPE = float(args.min_sharpe_select)
    REQ_POS_EXP = not args.no_require_pos_expectancy

    best_oos_sharpe = max([f.sharpe_test for f in folds], default=0.0)
    best_oos_exp    = max([f.exp_test for f in folds], default=0.0)
    total_oos_trades = sum([f.n_test for f in folds])

    guard_ok = (
        (chosen != "none")
        and (best_oos_sharpe >= MIN_OOS_SHARPE)
        and (total_oos_trades >= args.min_trades)
        and (best_oos_exp > 0 if REQ_POS_EXP else True)
    )

    guard_reject_reason = ""
    if not guard_ok:
        if chosen == "none":
            guard_reject_reason = "No viable strategy in folds"
        elif best_oos_sharpe < MIN_OOS_SHARPE:
            guard_reject_reason = f"Sharpe {best_oos_sharpe:.2f} < {MIN_OOS_SHARPE}"
        elif total_oos_trades < args.min_trades:
            guard_reject_reason = f"OOS trades {total_oos_trades} < {args.min_trades}"
        elif REQ_POS_EXP and best_oos_exp <= 0:
            guard_reject_reason = "OOS expectancy â‰¤ 0"

    # â”€â”€ Build live signal series for chosen strategy (or flat if guard failed)
    close, high, low = df["close"], df["high"], df["low"]
    if guard_ok:
        if chosen == "ma":
            ffast, fslow = _ma_params(args.interval)
            sig_series = moving_average_crossover(close, fast=ffast, slow=fslow,
                                                  allow_long=allow_long, allow_short=allow_short)
        elif chosen == "donchian":
            dn = _donchian_n(args.interval)
            sig_series = donchian_signal(high, low, close, n=dn,
                                         allow_long=allow_long, allow_short=allow_short)
        elif chosen == "rsi_mr":
            rl, lo, hi = _rsi_params(args.interval)
            sig_series = rsi_mr_signal(close, rsi_len=rl, os=lo, ob=hi,
                                       allow_long=allow_long, allow_short=allow_short)
        else:
            sig_series = pd.Series(0, index=close.index)
    else:
        chosen = "none"
        sig_series = pd.Series(0, index=close.index)

    last_sig = int(sig_series.iloc[-1])
    last_price = float(close.iloc[-1])
    ret_est = float(_pct_change(close).iloc[-1])

    # --- ML info for the UI (defaults)
    ml_info = {
        "enabled": bool(getattr(args, "ml_enable", False)),
        "p_up": None,
        "threshold": float(getattr(args, "ml_threshold", 0.55)),
        "model": None,
        "vote": None,               # "veto_down", "boost_up", "neutral", or None
    }

    # --- ML assist (optional) ---------------------------------
    ml_enabled = False
    ml_vote = None
    p_up = None
    model_path = ml_model_path(args.symbol, args.interval, args.ml_model_file)  # your helper

    if model_path.exists():
        try:
            p_up = predict_last_proba(model_path, df, horizon=args.ml_horizon)  # returns float in [0,1]
            ml_enabled = True
            # optional conservative gate (example: only allow LONG if p_up >= threshold)
            if last_sig > 0 and p_up < args.ml_threshold:
                last_sig = 0
                sig_text = "FLAT"
                ml_vote = f"veto long (p_up={p_up:.3f} < thr {args.ml_threshold:.2f})"
            elif last_sig == 0 and p_up >= args.ml_threshold:
                last_sig = 1
                sig_text = "LONG"
                ml_vote = f"boost long (p_up={p_up:.3f} â‰¥ thr {args.ml_threshold:.2f})"
            else:
                ml_vote = f"neutral (p_up={p_up:.3f})"
        except Exception as e:
            print(f"[ML] failed: {e}")


    if getattr(args, "ml_enable", False):
    # build default path if not provided
        if not getattr(args, "ml_model_file", None):
            sym = args.symbol.replace("/", "_")
            model_path = f"ml_models/{sym}_{args.interval}_lin.pkl"
        else:
            model_path = args.ml_model_file

        try:
            p_up = predict_last_proba(df, horizon=args.ml_horizon, model_path=model_path)
            thr = args.ml_threshold
            last_sig = int(sig_series.iloc[-1]) if len(sig_series) else 0

        # gate: veto or boost
            if last_sig > 0 and p_up < (1.0 - thr):
                # veto LONG to FLAT
                last_sig = 0
                sig_text = "FLAT"
                ml_vote = "veto_down"
            elif last_sig == 0 and p_up > thr:
                # boost FLAT to LONG
                last_sig = 1
                sig_text = "LONG"
                ml_vote = "boost_up"
            else:
                ml_vote = "neutral"

            ml_info.update({
                "p_up": float(p_up),
                "model": model_path,
                "vote": ml_vote,
            })

            print(f"[ML] p_up={p_up:.3f}  thr={thr}  model={model_path}")
        except Exception as e:
            # keep enabled flag but show model path / error for transparency
            ml_info.update({"model": model_path, "vote": f"error: {e.__class__.__name__}"})


    sig_text = {1: "LONG", -1: "SHORT", 0: "FLAT"}.get(last_sig, "FLAT")

    # â”€â”€ compute net returns and metrics for the chosen strategy
    # Note: only the last signal bar may be gated by ML; history is unaffected.
    sig_series = sig_series.copy()
    sig_series.iloc[-1] = last_sig
    ret_net_full, pos_full = pnl_from_signal(close, sig_series, fee_rate, slip_rate)
    metrics = compute_metrics(
        interval=args.interval,
        ret_net_full=ret_net_full,
        pos_full=pos_full,
        close_series=close,
        lookback=args.metrics_lookback,
    )

    def _bars_in_day(interval: str) -> int:
        interval = interval.strip().lower()
        if interval.endswith("m"):
            m = int(interval[:-1])
            return max(1, 1440 // max(1, m))
        if interval.endswith("h"):
            h = int(interval[:-1])
            return max(1, 24 // max(1, h))
        if interval.endswith("d"):
            return 1
        return 24  # fallback

    # ... inside main(), after pnl_from_signal(...) gives ret_net_full, pos_full
    bars_24h = min(len(pos_full), _bars_in_day(args.interval))

    # Count entries in the last 24h = transitions from 0 -> non-zero (LONG or SHORT)
    p = pos_full.fillna(0)
    entries_mask = (p.shift(1).fillna(0) == 0) & (p != 0)
    trades_24h = int(entries_mask.tail(bars_24h).sum())

    # (optional) you can expose more intraday fields later
    intraday = {"trades_24h": trades_24h}

    # â”€â”€ debug folds
    if args.debug_segments and folds:
        print("\n[WF Segments]")
        df_f = pd.DataFrame([asdict(f) for f in folds])
        with pd.option_context("display.max_rows", None, "display.width", 140):
            print(df_f.tail(12).to_string(index=False))

    # â”€â”€ emit JSON signal (NaN-safe)
    sig_path = Path(args.emit_json_file if args.emit_json else "brain_signal.json")
    payload = {
        "generated_at": _now_iso(),
        "exchange": args.exchange,
        "symbol": args.symbol,
        "interval": args.interval,
        "chosen_strategy": chosen,
        "signal": sig_text,
        "raw_signal": last_sig,
        "price": last_price,
        "entry_age_bars": args.entry_age,
        "run_ms": int((time.perf_counter() - t0) * 1000),
        "costs": {"fee": fee_rate, "slip": slip_rate},
        "folds": [asdict(f) for f in folds[-10:]],
        "selection_guard": {
            "passed": bool(guard_ok),
            "reason": guard_reject_reason,
            "best_oos_sharpe": None if math.isinf(best_oos_sharpe) else best_oos_sharpe,
            "best_oos_expect": None if math.isinf(best_oos_exp) else best_oos_exp,
            "total_oos_trades": total_oos_trades,
            "min_oos_sharpe": float(args.min_sharpe_select),
            "min_oos_trades": int(args.min_trades),
            "require_pos_expectancy": bool(REQ_POS_EXP),
        },
        "ml": ml_info,
        "regime_params": {
            "wf_train": wf_train,
            "wf_test":  wf_test,
            "wf_step":  wf_step,
            "adx_threshold": adx_th,
            "adx_len": adx_len,
            "auto_tuned": bool(auto_tuned),
        },
        "metrics": metrics,
        "intraday": intraday,
    }
    # put ML details into payload that the dashboard reads
    payload["ml"] = {
        "enabled": bool(ml_enabled),
        "p_up": float(p_up) if p_up is not None else None,
        "threshold": float(args.ml_threshold),
        "model": str(model_path) if model_path and model_path.exists() else None,
        "vote": ml_vote,
    }


    payload = sanitize(payload)

    if args.emit_json:
        sig_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # â”€â”€ optional paper equity update
    paper_equity_val: Optional[float] = None
    if args.paper_ledger:
        paper_fee = _slip_from_bps(args.paper_fee_bps) if args.paper_fee_bps is not None else fee_rate
        paper_slip = _slip_from_bps(args.paper_slip_bps) if args.paper_slip_bps is not None else slip_rate

        state_path = Path(args.paper_state_file)
        ledger_path = Path(args.paper_file)

        state = PaperState.load(state_path)
        state.reset_day_if_needed()

        if state.circuit_tripped():
            print("[CIRCUIT] Daily loss limit reached. Paper trading paused for the day.")
        else:
            equity_before = state.equity

            # flip cost if signal changed
            flip_cost = 0.0
            if len(sig_series) >= 2 and sig_series.iloc[-1] != sig_series.iloc[-2]:
                flip_cost = paper_fee + paper_slip

            # ATR-based sizing (signed by signal)
            pos_frac = 0.0
            if last_sig != 0:
                base_frac = position_size_from_atr(high, low, close, args.atr_len, args.risk, args.max_pos)
                pos_frac = base_frac * (1 if last_sig > 0 else -1)

            equity_after = equity_before * (1.0 + pos_frac * ret_est - flip_cost)
            state.equity = max(0.0, float(equity_after))
            state.last_update = _now_iso()
            state.save(state_path)

            append_paper_ledger(
                ledger_path=ledger_path,
                ts=state.last_update,
                symbol=args.symbol,
                signal=sig_text,
                price=last_price,
                ret_est=ret_est,
                equity_before=equity_before,
                equity_after=state.equity,
                pos_frac=pos_frac,
            )
            paper_equity_val = state.equity

    # â”€â”€ append metrics CSV (for dashboard)
    metrics_path = _metrics_path_from_signal(sig_path, args.metrics_file)
    append_metrics_csv(metrics_path, {
        "ts": _now_iso(),
        "exchange": args.exchange,
        "symbol": args.symbol,
        "interval": args.interval,
        "strategy": chosen,
        "signal": sig_text,
        "price": f"{last_price:.8f}",
        "bars_used": metrics.get("bars_used", 0),
        "ann_return": metrics.get("ann_return", 0.0),
        "ann_vol": metrics.get("ann_vol", 0.0),
        "sharpe_ann": metrics.get("sharpe_ann", 0.0),
        "max_drawdown": metrics.get("max_drawdown", 0.0),
        "win_rate_bar": metrics.get("win_rate_bar", 0.0),
        "profit_factor_bar": metrics.get("profit_factor_bar", 0.0),
        "trade_count": metrics.get("trade_count", 0),
        "avg_bar_return": metrics.get("avg_bar_return", 0.0),
        "paper_equity": f"{paper_equity_val:.2f}" if paper_equity_val is not None else "",
    })

    # â”€â”€ optional: persist effective params (so future runs can reuse them)
    if args.persist_params:
        persist_params(
            args.symbol,
            args.interval,
            {
                "wf_train": wf_train,
                "wf_test": wf_test,
                "wf_step": wf_step,
                "adx_trend_threshold": adx_th,
                "adx_len": adx_len,
                "chosen_strategy": chosen,
                "persisted_at": _now_iso(),
            }
        )

    # â”€â”€ banner (friendly console summary)
    print("\n====== BRAIN DECISION ======")
    print(f"Time:   {_now_iso()}")
    print(f"Pair:   {args.symbol}  TF: {args.interval}  Strategy: {chosen.upper()}")
    print(f"Signal: {sig_text}     Price: {last_price:.6f}")
    if args.emit_json:
        print(f"Signal JSON emitted to:      {sig_path.name}")
    print(f"Metrics appended to:         {metrics_path.name}")

    if args.paper_ledger:
        print(f"Paper equity state saved to: {args.paper_state_file}")

    # Show guard & ML hints (compact)
    if not guard_ok:
        print(f"[GUARD] Selection rejected â†’ FLAT. Reason: {guard_reject_reason}")
    if ml_info.get("p_up") is not None:
        print(f"[ML] p_up={ml_info['p_up']:.3f}  thr={ml_info['threshold']:.2f}  model={ml_info.get('model')}")

    # done


if __name__ == "__main__":
    main()

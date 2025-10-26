import time
import os
import json
from dotenv import load_dotenv
import pandas as pd
from bot.exchange import Exchange, PaperExchange
from db.db_manager import DBManager
from strategy.trade_logic import simple_moving_average_strategy
from utils.logger import get_logger
from core.risk import RiskConfig, compute_atr, position_size_usd
from core.regime import compute_regime
from core.breaker import BreakerConfig, BreakerState, update_breaker
from core.runtime_state import write_last, RUNTIME_DIR as RT_DIR
from core.portfolio import rolling_corr_guard
from strategy.selector import pick_by_regime
from core.persistence import record_equity, open_trade_if_none, close_trade_for_symbol
from core.ml.features import basic_features
from core.ml.gate import apply_ml_gate
from core.ml.model_io import load_model, predict_p_up
from core.runtime_state import read_news_multiplier
from core.risk_profile import pick_profile
from pathlib import Path
KILL_FILE = Path("runtime") / "killswitch.on"

# Load .env variables for keys and secrets
load_dotenv()

# Initialize module-specific logger
logger = get_logger(__name__)

class ExecutionEngine:
    def __init__(self):
        # Initialize MEXC exchange wrapper
        mode = os.getenv("MODE", "PAPER").upper()
        if mode == "PAPER":
            # Use the paper exchange that persists to DB
            try:
                self.exchange = PaperExchange()
            except Exception:
                self.exchange = Exchange()
        else:
            self.exchange = Exchange()
        # Initialize database
        self.db = DBManager()
        # Default trading symbol
        self.symbol = 'BTC/USDT'
        # optional ML model
        try:
            self._ml_model = load_model()
        except Exception:
            self._ml_model = None
        # lazy-initialized strategy selector and decision logger (non-invasive)
        self._strategy_selector = None
        self._decision_logger = None

    def _flatten_symbol(self, symbol: str) -> None:
        """
        Close position for symbol. In this codebase, Exchange is a thin wrapper;
        if a broker interface exists in your environment, call it. Fail-soft if not available.
        """
        try:
            # Placeholder: integrate with your real broker if available
            if hasattr(self, "broker") and hasattr(self.broker, "get_position"):
                pos = self.broker.get_position(symbol)
                if not pos or abs(float(pos.get("qty", 0.0))) <= 0:
                    return
                side = "sell" if str(pos.get("side", "")).lower() == "long" else "buy"
                qty = abs(float(pos.get("qty", 0.0)))
                if hasattr(self.broker, "place_market_order"):
                    self.broker.place_market_order(symbol=symbol, side=side, qty=qty)
        except Exception:
            pass

    def run_once(self, is_mock=True):
        """
        Runs one cycle of signal evaluation and order execution (mock/testing mode).
        """
        logger.info(f"Evaluating signal for {self.symbol}...")

        # Fetch mock OHLCV data (candle data)
        ohlcv = self.exchange.fetch_ohlcv(self.symbol)
        if not ohlcv:
            logger.warning("⚠️ No OHLCV data received. Skipping this run.")
            return

        # Apply strategy to get signal
        signal = simple_moving_average_strategy(ohlcv)
        logger.info(f"[SMA] Signal: {signal}")

        if signal in ['buy', 'sell']:
            current_price = ohlcv[-1][4]  # last candle close price
            quantity = 0.01  # mock quantity (BTC)
            trade_id = f"{signal}_{int(time.time())}"
            status = 'FILLED' if is_mock else 'SUBMITTED'
            # Record mock trade in DB
            self.db.insert_trade(
                trade_id=trade_id,
                symbol=self.symbol,
                side=signal.upper(),
                price=current_price,
                amount=quantity,
                status=status,
                is_mock=1 if is_mock else 0
            )
        else:
            logger.info("🟡 No trade signal. Holding position.")
    def run_live(self, symbol="BTCUSDT", trade=False):
        """
        Runs live signal evaluation and (optionally) executes a trade.

        Args:
            symbol (str): Trading pair (e.g., BTCUSDT)
            trade (bool): Whether to execute a live trade
        """
        logger.info(f"Running LIVE execution for {symbol} (trade={trade})")

        # Get real candle data
        ohlcv = self.exchange.fetch_ohlcv(symbol, use_live=True)
        if not ohlcv:
            logger.warning("⚠️ Failed to fetch live OHLCV data.")
            return

        # Normalize OHLCV into a DataFrame for downstream computations
        try:
            if isinstance(ohlcv, list) and ohlcv and not hasattr(ohlcv, "__dataframe__"):
                df = pd.DataFrame(ohlcv, columns=["ts","open","high","low","close","vol"]).astype({"close": float, "high": float, "low": float})
            else:
                df = pd.DataFrame(ohlcv)
                if set(["close","high","low"]) - set(df.columns):
                    df = df.rename(columns={0:"ts",1:"open",2:"high",3:"low",4:"close",5:"vol"})
        except Exception:
            df = None

        # Compute regime and pick strategy by regime
        reg = compute_regime(df if df is not None else ohlcv)
        # Emit a raw strategy signal for analytics/labeling using the new
        # engine_strategy_wiring helpers. This is intentionally non-invasive
        # and wrapped in try/except so it never affects runtime logic.
        try:
            if self._strategy_selector is None:
                try:
                    from core.engine_strategy_wiring import make_strategy_selector

                    self._strategy_selector = make_strategy_selector()
                except Exception:
                    self._strategy_selector = None
            if self._decision_logger is None:
                # lightweight adapter exposing write(row) -> save_decision_row(row)
                class _DecisionLogger:
                    def write(self, r):
                        try:
                            from db.db_manager import save_decision_row

                            save_decision_row(r)
                        except Exception:
                            try:
                                logger.info("[RawSignal] save_decision_row failed", exc_info=True)
                            except Exception:
                                pass

                self._decision_logger = _DecisionLogger()

            # prepare OHLCV arrays expected by adapter
            o_arr = h_arr = l_arr = c_arr = v_arr = []
            if df is not None and not df.empty:
                o_arr = df.get("open", []).tolist()
                h_arr = df.get("high", []).tolist()
                l_arr = df.get("low", []).tolist()
                c_arr = df.get("close", []).tolist()
                v_arr = df.get("vol", []).tolist() if "vol" in df.columns else [0] * len(c_arr)
            elif isinstance(ohlcv, list) and ohlcv:
                o_arr = [x[1] for x in ohlcv]
                h_arr = [x[2] for x in ohlcv]
                l_arr = [x[3] for x in ohlcv]
                c_arr = [x[4] for x in ohlcv]
                v_arr = [x[5] if len(x) > 5 else 0 for x in ohlcv]

            if self._strategy_selector is not None:
                try:
                    from core.engine_strategy_wiring import pick_and_log_strategy_signal

                    pick_and_log_strategy_signal(
                        self._strategy_selector,
                        symbol,
                        reg.label,
                        o_arr,
                        h_arr,
                        l_arr,
                        c_arr,
                        v_arr,
                        int(time.time()),
                        self._decision_logger,
                    )
                except Exception:
                    # never let analytics emission break execution
                    pass
        except Exception:
            pass
        strat_name, strat_fn = pick_by_regime(reg.label)
        try:
            _df = df
            if _df is None and isinstance(ohlcv, list) and ohlcv:
                _df = pd.DataFrame(ohlcv, columns=["ts","open","high","low","close","vol"]).astype({"close": float, "high": float, "low": float})
            signal = strat_fn(_df) if _df is not None else "hold"
        except Exception:
            signal = "hold"
        logger.info(f"[Strategy:{strat_name}] Signal for {symbol}: {signal.upper()}")

        # Trade-dependence veto: after a winner, skip next breakout entry
        try:
            if signal in ("buy", "sell") and strat_name in ("donchian_close",):
                from core.rules.trade_dependence import veto_after_winner
                reason = veto_after_winner(symbol, self.db)
                if reason:
                    if 'reasons' not in locals() or not isinstance(reasons, list):
                        reasons = []
                    reasons.append(reason)
                    signal = "hold"
        except Exception:
            pass

        # Collect gating reasons for traceability
        reasons: list[str] = []

        # --- ML gate (prefer sklearn model proba if available; fallback to heuristic) ---
        ml_p_up = None
        ml_vote = "neutral"
        prev_signal = signal
        try:
            _df2 = df
            if _df2 is None and isinstance(ohlcv, list) and ohlcv:
                _df2 = pd.DataFrame(ohlcv, columns=["ts","open","high","low","close","vol"]).astype({"close": float, "high": float, "low": float})
            if _df2 is not None and not _df2.empty:
                feats = basic_features(_df2)
                if getattr(self, "_ml_model", None) is not None:
                    ml_p_up = predict_p_up(self._ml_model, feats.iloc[-1])
                if ml_p_up is None:
                    # fallback heuristic if no model or prediction failure
                    ema_slope = float(feats["ema_slope"].iloc[-1])
                    rsi = float(feats["rsi14"].iloc[-1])
                    vol = float((feats["vol30"].iloc[-1] or 0.0))
                    ret_std = float(_df2["close"].astype(float).pct_change().std() or 1e-8)
                    s = (ema_slope / max(1e-8, abs(ret_std))) + ((rsi - 50.0) / 50.0) - min(3.0, vol * 10.0)
                    ml_p_up = 1.0 / (1.0 + (2.718281828 ** (-s)))
                import os as _os
                thr = float(_os.getenv("ML_PROB_THRESHOLD", "0.55"))
                signal, ml_vote = apply_ml_gate(signal, ml_p_up, thr)
                if prev_signal in ("buy","sell") and signal == "hold":
                    reasons.append("ml_veto")
        except Exception:
            pass

        # Regime gate (block only during panic; chop will route to mean reversion)
        if reg.label == "panic":
            logger.info(f"[Regime] {reg.label}. Blocking entries.")
            signal = "hold"
            reasons.append(f"regime:{reg.label}")

        # Hard kill-switch gate
        if KILL_FILE.exists():
            try:
                self._flatten_symbol(symbol)
            except Exception:
                pass
            signal = "hold"
            reasons.append("killswitch")

        # Self-tuning panic band based on ATR and equity-aware profile
        try:
            # Use latest equity to pick profile
            equity_val = float(self.db.get_latest_equity()) if hasattr(self.db, "get_latest_equity") else 0.0
            profile_for_panic = pick_profile(equity_val if equity_val > 0 else 1000.0)
            if df is not None and not df.empty and signal in ("buy","sell"):
                import numpy as _np
                price_now = float(df["close"].iloc[-1])
                # recent high over a short window
                recent_high = float(_np.nanmax(df["high"].tail(100))) if "high" in df.columns else price_now
                drawdown = (recent_high - price_now) / recent_high if recent_high else 0.0
                # ATR-based volatility band
                try:
                    atr_series = compute_atr(df, n=14)
                    atr_latest = float(atr_series.iloc[-1]) if len(atr_series) else 0.0
                except Exception:
                    atr_latest = 0.0
                vol = (atr_latest / price_now) if price_now > 0 else 0.0
                thr = max(0.01, vol) * float(getattr(profile_for_panic, "panic_atr_mult", 3.0))
                if drawdown >= thr:
                    logger.info(f"[PanicBand] drawdown={drawdown:.4f} >= thr={thr:.4f}. Holding.")
                    signal = "hold"
                    reasons.append("panic_band")
        except Exception:
            pass

        # Update breaker from equity and regime
        equity = self.db.get_latest_equity() if hasattr(self.db, "get_latest_equity") else None
        if not hasattr(self, "_breaker_state"):
            self._breaker_state = BreakerState()
            self._breaker_cfg = BreakerConfig()
        eq = float(equity or 0.0)
        # persist equity snapshot (safe no-op if DB missing)
        try:
            if eq > 0:
                record_equity(eq)
        except Exception:
            pass
        # update breaker with profile-aware DLL
        try:
            _equity_for_profile = float(eq or 0.0)
            _profile_tmp = pick_profile(_equity_for_profile if _equity_for_profile > 0 else 1000.0)
            # configure DLL in breaker (expects fraction, not percent)
            self._breaker_cfg.max_daily_loss_pct = float(_profile_tmp.max_daily_loss_pct) / 100.0
            self._breaker_cfg.auto_flatten_on_dll = bool(_profile_tmp.auto_flatten_on_dll)
        except Exception:
            pass
        self._breaker_state = update_breaker(self._breaker_state, eq, reg.label, self._breaker_cfg)
        if self._breaker_state.active:
            logger.info("[Breaker] Active. Forcing hold.")
            signal = "hold"
            try:
                reasons.append(f"breaker:{getattr(self._breaker_state,'last_reason', None) or 'active'}")
            except Exception:
                reasons.append("breaker:active")

        # Correlation guard - optional, skip if highly correlated with holdings
        try:
            held_symbols = []
            # Pull currently open symbols from DB if available
            if hasattr(self.db, "get_open_positions"):
                try:
                    pos = self.db.get_open_positions() or []
                    held_symbols = [p.get("symbol") for p in pos if isinstance(p, dict) and p.get("symbol")]
                except Exception:
                    held_symbols = []
            returns_map = {}
            if (signal in ("buy", "sell")) and held_symbols:
                # fetch same timeframe N bars to align returns
                N = 500
                tf = getattr(self.exchange, "timeframe", None)
                # current symbol
                ohlcv_cur = self.exchange.fetch_ohlcv(symbol, use_live=True, timeframe=tf, limit=N)
                if ohlcv_cur:
                    df_cur = pd.DataFrame(ohlcv_cur, columns=["ts","open","high","low","close","vol"])
                    returns_map[symbol] = df_cur["close"].astype(float).pct_change()
                # peer symbols
                for s in held_symbols:
                    if s == symbol:
                        continue
                    try:
                        ohl = self.exchange.fetch_ohlcv(s, use_live=True, timeframe=tf, limit=N)
                        if not ohl:
                            continue
                        d = pd.DataFrame(ohl, columns=["ts","open","high","low","close","vol"])
                        returns_map[s] = d["close"].astype(float).pct_change()
                    except Exception:
                        continue
                if not rolling_corr_guard(returns_map, symbol, held_symbols, lookback=480, threshold=0.85):
                    logger.info("[Correlation] Highly correlated to existing exposure. Skipping.")
                    signal = "hold"
                    reasons.append("correlation")
        except Exception as e:
            logger.info(f"[Correlation] guard skipped: {e}")

        intent = signal
        notional = 0.0
        stop_level = None
        tp_level = None
        # Shorts disabled gate (optional via env ALLOW_SHORTS)
        if signal == "sell" and os.getenv("ALLOW_SHORTS", "true").lower() in ("0","false","no"):
            reasons.append("shorts_disabled")
            signal = "hold"

        if signal in ["buy", "sell"]:
            if trade:
                # ATR sizing to pick a notional
                try:
                    import pandas as _pd
                    # If ohlcv is a list-of-lists, convert to DataFrame with close/high/low
                    if isinstance(ohlcv, list) and ohlcv and not hasattr(ohlcv, "__dataframe__"):
                        df = _pd.DataFrame(ohlcv, columns=["ts","open","high","low","close","vol"]).astype({"close": float, "high": float, "low": float})
                    else:
                        df = _pd.DataFrame(ohlcv)
                        if set(["close","high","low"]) - set(df.columns):
                            df = df.rename(columns={0:"ts",1:"open",2:"high",3:"low",4:"close",5:"vol"})

                    atr = compute_atr(df, n=14).iloc[-1]
                    price = float(df["close"].iloc[-1])
                except Exception:
                    # Fallback if compute fails
                    atr = None
                    price = float(ohlcv[-1][4]) if isinstance(ohlcv, list) and ohlcv else 0.0

                equity_usd = float(eq or 10000.0)
                profile = pick_profile(equity_usd)
                news_mult = read_news_multiplier(1.0)
                base_notional = position_size_usd(
                    equity_usd=equity_usd,
                    price=price,
                    atr_latest=(float(atr) if atr is not None else None),
                    cfg=RiskConfig(),
                    leverage_limit=None,
                    existing_symbol_gross_usd=0.0,
                )
                # planned stop/tp levels based on ATR multiples
                try:
                    if atr is not None:
                        atr_val = float(atr)
                        if signal == "buy":
                            stop_level = price - 2.0 * atr_val
                            tp_level = price + 4.0 * atr_val
                        else:
                            stop_level = price + 2.0 * atr_val
                            tp_level = price - 4.0 * atr_val
                except Exception:
                    pass
                # per-trade risk cap via stop distance
                try:
                    desired = float(base_notional) * float(profile.risk_multiplier)
                    pre_cap = desired
                    if stop_level is not None:
                        stop_dist = abs(price - float(stop_level))
                        risk_cap_usd = equity_usd * (float(profile.risk_per_trade_pct) / 100.0)
                        qty_risk_cap = (risk_cap_usd / max(1e-8, stop_dist)) if stop_dist > 0 else 0.0
                        notional_risk_cap = qty_risk_cap * price
                        pre_cap = min(desired, notional_risk_cap)
                    gross_cap = equity_usd * float(profile.leverage_max)
                    notional = min(pre_cap * float(news_mult), gross_cap)
                except Exception:
                    # fallback to base with news multiplier
                    notional = float(base_notional) * float(news_mult)
                if notional <= 0:
                    logger.info("[Sizing] Notional too small. Skipping trade.")
                    reasons.append("size=0")
                else:
                    # Execute using paper exchange if available; otherwise fall back to mock place_market_order
                    if signal == "buy":
                        try:
                            if isinstance(self.exchange, PaperExchange):
                                self.exchange.buy_notional(symbol, notional, price)
                            else:
                                self.exchange.place_market_order(symbol, "buy", notional)
                            logger.info(f"BUY {symbol} notional {notional:.2f} USD")
                        except Exception:
                            logger.exception("paper BUY failed")
                        # record open trade (qty approximated)
                        try:
                            qty = notional / price if price > 0 else 0.0
                            open_trade_if_none(symbol=symbol, side="buy", qty=qty, price=price)
                        except Exception as e:
                            logger.info(f"[DB] open trade skipped: {e}")
                    else:
                        # for sell we assume we hold qty ~ notional/price
                        qty = notional / price if price > 0 else 0.0
                        try:
                            if isinstance(self.exchange, PaperExchange):
                                self.exchange.sell_qty(symbol, qty, price)
                            else:
                                self.exchange.place_market_order(symbol, "sell", qty)
                            logger.info(f"SELL {symbol} qty {qty:.6f}")
                        except Exception:
                            logger.exception("paper SELL failed")
                        # close most recent open trade for this symbol
                        try:
                            pnl = close_trade_for_symbol(symbol=symbol, exit_price=price)
                            if pnl is not None:
                                logger.info(f"[DB] closed trade for {symbol}, pnl={pnl:.2f}")
                        except Exception as e:
                            logger.info(f"[DB] close trade skipped: {e}")
            else:
                logger.info("Trade signal received but live trading is DISABLED.")
                reasons.append("trade=False")
        else:
            logger.info("No trade signal. Holding position.")

        # Final decision trace (after sizing)
        try:
            logger.info(f"[Decision] {symbol} signal={signal} reasons={','.join(reasons) or 'ok'} size={notional:.2f}")
        except Exception:
            pass

        # Persist a lightweight snapshot for the dashboard
        try:
            last_price = 0.0
            if df is not None and not df.empty:
                last_price = float(df["close"].iloc[-1])
            elif isinstance(ohlcv, list) and ohlcv:
                last_price = float(ohlcv[-1][4])
            write_last(symbol, {
                "regime": reg.label,
                "strategy": strat_name,
                "breaker": {
                    "active": bool(getattr(self._breaker_state, "active", False)),
                    "cooldown_until": getattr(self._breaker_state, "cooldown_until", None).isoformat() if getattr(self._breaker_state, "cooldown_until", None) else None,
                    "reason": getattr(self._breaker_state, "last_reason", None),
                },
                "intent": intent,
                "ml_p_up": ml_p_up,
                "ml_vote": ml_vote,
                "gate_reason": ("".join([]) if not reasons else ",".join([r for r in reasons if r])) or None,
                "sized_notional_usd": float(notional),
                "news_multiplier": float(read_news_multiplier(1.0)),
                "price": last_price,
                "planned_stop": float(stop_level) if stop_level is not None else None,
                "planned_tp": float(tp_level) if tp_level is not None else None,
                "risk_profile": profile.name if 'profile' in locals() else None,
            })
            logger.info(f"[Runtime] snapshot written for {symbol}")
        except Exception as e:
            logger.info(f"[Runtime] snapshot write skipped: {e}")

        # Persist decision row for analytics (never break loop on failure)
        try:
            from db.db_manager import save_decision_row
            save_decision_row({
                "ts": int(time.time()),
                "symbol": symbol,
                "strategy": strat_name,
                "regime": reg.label,
                "signal": signal,
                "intent": intent,
                "size_usd": float(notional),
                "price": last_price,
                "ml_p_up": ml_p_up,
                "ml_vote": ml_vote,
                "veto": any(r in ("ml_veto","trade=False","killswitch","breaker:active") or r.startswith("breaker:") for r in reasons),
                "reasons": ("".join([]) if not reasons else ",".join([r for r in reasons if r])) or "ok",
                "planned_stop": float(stop_level) if stop_level is not None else None,
                "planned_tp": float(tp_level) if tp_level is not None else None,
                "run_id": os.getenv("RUN_ID"),
            })
        except Exception:
            try:
                logger.info("[DecisionLog] save_decision_row failed", exc_info=True)
            except Exception:
                pass

    def fetch_latest_mid_prices(self, symbols: list[str]) -> dict[str, float]:
        out: dict[str, float] = {}
        try:
            for s in symbols:
                ohlcv = self.exchange.fetch_ohlcv(s, use_live=True, timeframe=getattr(self.exchange, "timeframe", None), limit=1)
                if ohlcv:
                    o, h, l, c = [float(x) for x in ohlcv[-1][1:5]]
                    out[s] = (o + h + l + c) / 4.0
        except Exception:
            pass
        return out

    def write_account_runtime(self, prices: dict[str, float] | None = None, override: dict | None = None) -> None:
        """
        Publish account-level runtime (equity, cash, exposure_usd, positions[]) and
        persist an equity snapshot to the persistence DB. Fail-soft by design.
        """
        try:
            if override is not None:
                snap = {"ts": time.time(), **override}
            else:
                # Prefer exchange account overview with provided prices for MTM
                acct = None
                if hasattr(self.exchange, "account_overview"):
                    try:
                        if isinstance(self.exchange, PaperExchange):
                            acct = self.exchange.account_overview(prices or {})
                        else:
                            acct = self.exchange.account_overview()
                    except Exception:
                        acct = None
                if acct is None:
                    # minimal fallback
                    equity_val = self.db.get_latest_equity() or 0.0
                    snap = {"ts": time.time(), "equity": float(equity_val), "cash": float(equity_val), "exposure_usd": 0.0, "positions": []}
                else:
                    snap = {"ts": time.time(), **acct}
            # Write to the shared runtime directory
            try:
                (RT_DIR).mkdir(parents=True, exist_ok=True)
                (RT_DIR / "account_runtime.json").write_text(json.dumps(snap), encoding="utf-8")
            except Exception:
                pass
            # Persist equity snapshot via core.persistence
            try:
                if snap["equity"] > 0:
                    try:
                        from db.db_manager import save_equity_snapshot
                        save_equity_snapshot(float(snap["equity"]), int(snap["ts"]))
                    except Exception:
                        pass
                    from core.persistence import record_equity
                    record_equity(float(snap["equity"]))
            except Exception:
                pass
        except Exception:
            # Never let diagnostics break the loop
            pass

    def close(self):
        """
        Close database connection and clean up.
        """
        self.db.close()
        logger.info("✅ Resources released cleanly.")

from __future__ import annotations

import time
from decimal import Decimal, getcontext
from typing import Any, List, Optional
from dotenv import load_dotenv
import os

from core.risk_adaptive import AdaptiveRiskEngineV2
from core.strategy_selector_v2 import StrategySelectorV2
from utils.logger import logger, setup_logger, log_json, log_extra
from core.paper_executor_v2 import PaperExecutorV2
from core.execution_router_v2 import ExecutionRouterV2

# ML meta-signal components
from core.ml import (
    MetaSignalFeatureExtractor,
    get_ranker,
    apply_ml_gate,
)
from ops.notifier import get_notifier
from core.risk.engine_v3 import RiskEngineV3

# Minimal exchange stub (tests patch the real exchange)
try:
    from exchange.paper import PaperExchange
except Exception:
    class PaperExchange:
        def __init__(self):
            pass

# For unittest.mock.patch("core.execution_engine.Exchange")
Exchange = PaperExchange

# Minimal DB stub
try:
    from db.db_manager import DBManager
except Exception:
    class DBManager:
        def __init__(self):
            pass

        def insert_trade(self, *args, **kwargs):
            return


logger = setup_logger(__name__)
getcontext().prec = 28


class EngineState:
    def __init__(self) -> None:
        self.last_signal = None
        self.last_regime = None
        self.consecutive_losses = 0
        self.position_size = 0
        self.volatility_anomaly = False
        self.ml_veto_spikes = 0


def simple_moving_average_strategy(*args, **kwargs):
    """
    Tests patch this to return buy/sell/hold.
    Default implementation does nothing.
    """
    return "hold"


class ExecutionEngine:
    """
    Clean ExecutionEngine (Hybrid C2)
    ---------------------------------

    This is the authoritative engine used by:
      - unit tests
      - API demo routes
      - backtest harness

    It integrates:
      - StrategySelectorV2 → S3 strategy outputs (stored only)
      - Risk Engine v2 (ATR/Return-vol hybrid)
      - Drawdown guards
      - Loss-streak kill switch
      - Exposure caps
      - Test-patchable strategy (for test suite compliance)

    DOES NOT route real orders yet (Phase 4.B).
    """

    def __init__(self):
        load_dotenv()

        # Runtime config
        self.symbol = "BTC/USDT"
        self.exchange = PaperExchange()
        self.db = DBManager()

        # Engine state
        self.last_signal: str = "hold"
        self.last_regime: str = "normal"

        # Strategy Selector (Phase 4)
        self.strategy_selector = StrategySelectorV2()

        # Execution Router (Phase 4.B)
        self.execution_router = ExecutionRouterV2(self.exchange)
        self.last_router_directive = {
            "action": "hold",
            "side": None,
            "qty": Decimal("0"),
            "entry_price": Decimal("0"),
            "stop": Decimal("0"),
            "source": "router_v2",
            "meta": {},
        }

        # Paper Executor (Phase 4.B-3)
        self.paper_executor = PaperExecutorV2()
        # Current equity (live from paper executor)
        self.current_equity: Decimal = Decimal("10000")
        self.last_execution_state = {
            "side": None,
            "qty": 0.0,
            "entry_price": 0.0,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "equity_now": 10000.0,
        }

        # S3 strategy metadata
        self.last_intent: str = "flat"
        self.last_strength: Decimal = Decimal("0")
        self.last_stop: Decimal = Decimal("0")
        self.last_entry_price: Decimal = Decimal("0")
        self.last_exit_price: Decimal = Decimal("0")
        self.last_strategy_meta: dict = {}

        # TTL memory (legacy compatibility)
        self._signal_memory = {"last_signal": None, "ttl_remaining": 0}

        # ML
        self._ml_extractor = MetaSignalFeatureExtractor()
        self._ml_ranker = get_ranker()
        self.last_ml_score: float = 0.5
        self.last_ml_action: str = "none"
        self.last_ml_effective_size: str = "0"

        # Risk Engine v2
        self.risk_v2_enabled: bool = False
        self.risk_engine_v2 = AdaptiveRiskEngineV2()

        # ------------------------------------------------------------
        # Phase 6.C-2: Risk Engine V3 activation flag (default OFF)
        # ------------------------------------------------------------
        self.risk_v3_enabled: bool = False

        # ------------------------------------------------------------
        # Phase 6.E-2 — Insight Engine attachment (default OFF)
        # ------------------------------------------------------------
        self.insight_enabled: bool = False
        try:
            from insight.engine import InsightEngine
            self.insight = InsightEngine()
        except Exception:
            self.insight = None

        # Track per-position high/low since entry
        self._trade_trackers = {}   # trade_id -> {entry, high, low, strategy, regime}
        self._current_trade_id: Optional[str] = None

        # RiskEngineV3 scaffold. Does not change behavior until Phase 6 logic is added.
        try:
            self.risk_v3 = RiskEngineV3()
        except Exception:
            # keep backward compatibility if scaffold is not available
            self.risk_v3 = None

        # If scaffolded, propagate engine caps into V3 defaults
        try:
            if getattr(self, "risk_v3", None) is not None:
                try:
                    # fractions consistent with existing V2 settings
                    self.risk_v3.global_cap = self.global_portfolio_limit
                    self.risk_v3.symbol_cap = self.per_symbol_exposure_limit
                except Exception:
                    pass
        except Exception:
            pass

        # Exposure limits
        self.per_symbol_exposure_limit: Decimal = Decimal("0.25")
        self.global_portfolio_limit: Decimal = Decimal("0.50")

        # Drawdown state
        self.max_equity_seen: Decimal = Decimal("0")
        self.current_drawdown: Decimal = Decimal("0")
        self.soft_dd_threshold: Decimal = Decimal("0.10")
        self.hard_dd_threshold: Decimal = Decimal("0.25")

        # Loss streak
        self.max_consecutive_losses: int = 4
        self._loss_streak: int = 0
        self._prior_equity: Decimal = Decimal("0")

        # Risk-off
        self.risk_off: bool = False
        self.global_risk_off: bool = False

        # Orchestrator pause callback
        self.pause_callback = None

        # Engine health state for APIs
        try:
            self.state = EngineState()
        except Exception:
            self.state = None

    # -------------------------------------------------------------------
    # Drawdown & Loss Streak
    # -------------------------------------------------------------------
    def _update_drawdown_state(self, equity: Decimal) -> None:
        try:
            if equity > self.max_equity_seen:
                self.max_equity_seen = equity

            if self.max_equity_seen > 0:
                self.current_drawdown = (
                    self.max_equity_seen - equity
                ) / self.max_equity_seen
            else:
                self.current_drawdown = Decimal("0")
        except Exception:
            self.current_drawdown = Decimal("0")

    def _update_loss_streak(self, equity: Decimal) -> None:
        try:
            if self._prior_equity == Decimal("0"):
                self._prior_equity = equity
                return

            if equity < self._prior_equity:
                self._loss_streak += 1
            elif equity > self._prior_equity:
                self._loss_streak = 0

            self._prior_equity = equity
        except Exception:
            return

    # -------------------------------------------------------------------
    # Risk Engine v2 sizing
    # -------------------------------------------------------------------
    def _compute_position_size(
        self,
        signal: Any,
        ohlcv: List[list],
        equity: Decimal,     # engine will pass current_equity
        price: float,
        regime: Optional[str] = None,
    ) -> Decimal:

        # ============================================================
        # PHASE 6.C-2 — Risk Engine V3 activation pipeline
        # If enabled, attempt to compute size via RiskEngineV3. Any
        # failure falls back to the existing V2 pipeline.
        # ============================================================
        if getattr(self, "risk_v3_enabled", False):
            try:
                # Prepare inputs
                price_dec = Decimal(str(price))
                equity_dec = Decimal(str(equity))
                regime_label = regime or self.last_regime

                # Fetch current symbol exposure (best-effort)
                try:
                    acct = self.exchange.account_overview()
                    positions = {
                        p.get("symbol"): Decimal(str(p.get("qty", "0")))
                        for p in acct.get("positions", [])
                        if isinstance(p, dict)
                    }
                except Exception:
                    positions = {}

                # Apply risk engine (use existing apply signature)
                try:
                    prices_dec = [Decimal(str(c[4])) for c in ohlcv[-20:]] if ohlcv else []
                except Exception:
                    prices_dec = []

                try:
                    rinfo = self.risk_v3.apply(
                        self.symbol,
                        signal,
                        prices_dec,
                        positions,
                    ) if getattr(self, "risk_v3", None) is not None else {}
                except Exception:
                    rinfo = {}

                # Compute desired notional via sizer (conservative interpretation)
                try:
                    vol = rinfo.get("volatility", Decimal("0"))
                    exposure_caps = rinfo.get("exposure_caps", {}) or {}
                    frac_or_notional = self.risk_v3.sizer.compute_size(
                        self.symbol,
                        signal,
                        vol,
                        exposure_caps,
                        equity_dec,
                        positions.get(self.symbol, Decimal("0")),
                        panic=rinfo.get("panic", False) if isinstance(rinfo, dict) else False,
                    )
                except Exception:
                    frac_or_notional = Decimal("0")

                # Interpret returned value: treat <=1 as fraction of equity
                try:
                    if isinstance(frac_or_notional, Decimal) and frac_or_notional <= Decimal("1"):
                        notional = equity_dec * frac_or_notional
                    else:
                        notional = Decimal(str(frac_or_notional))
                except Exception:
                    notional = Decimal("0")

                # Convert notional → qty
                if price_dec > 0:
                    return (notional / price_dec).quantize(Decimal("0.00000001"))
                return Decimal("0")

            except Exception:
                # Fail-safe: fall back to V2
                pass

        if not self.risk_v2_enabled:
            return Decimal("0")

        self._update_drawdown_state(equity)
        self._update_loss_streak(equity)

        # Risk off
        if self.risk_off or self.global_risk_off:
            return Decimal("0")

        # Loss streak kill
        if self._loss_streak >= self.max_consecutive_losses:
            if callable(self.pause_callback):
                try:
                    self.pause_callback()
                except Exception:
                    pass
            return Decimal("0")

        # Hard DD kill
        if self.current_drawdown >= self.hard_dd_threshold:
            if callable(self.pause_callback):
                try:
                    self.pause_callback()
                except Exception:
                    pass
            return Decimal("0")

        try:
            highs = [row[2] for row in ohlcv]
            lows = [row[3] for row in ohlcv]
            closes = [row[4] for row in ohlcv]
        except Exception:
            return Decimal("0")

        eq_dec = Decimal(str(equity))
        price_dec = Decimal(str(price))

        # Use selector regime primarily
        regime_label = self.last_regime

        try:
            notional = self.risk_engine_v2.compute(
                highs,
                lows,
                closes,
                regime_label,
                eq_dec,
                price_dec,
            )
        except Exception:
            return Decimal("0")

        if not isinstance(notional, Decimal):
            notional = Decimal(str(notional))

        # Soft DD scaling
        if self.current_drawdown >= self.soft_dd_threshold:
            dd_span = self.hard_dd_threshold - self.soft_dd_threshold
            if dd_span > 0:
                factor = (
                    self.hard_dd_threshold - self.current_drawdown
                ) / dd_span
                factor = max(Decimal("0"), min(Decimal("1"), factor))
                notional *= factor

        # Exposure caps
        per_symbol_max = eq_dec * self.per_symbol_exposure_limit
        if notional > per_symbol_max:
            notional = per_symbol_max

        try:
            acct = self.exchange.account_overview()
            global_exposure = Decimal(str(acct.get("total_exposure", "0")))
        except Exception:
            global_exposure = Decimal("0")

        global_max = eq_dec * self.global_portfolio_limit
        headroom = max(Decimal("0"), global_max - global_exposure)
        if notional > headroom:
            notional = headroom

        if price_dec > 0:
            return (notional / price_dec).quantize(Decimal("0.00000001"))

        return Decimal("0")

    # -------------------------------------------------------------------
    # Test-mode run_once
    # -------------------------------------------------------------------
    def run_once(self, is_mock: bool = True, cid: str | None = None) -> bool:
        try:
            if is_mock:
                ohlcv = PaperExchange.fetch_ohlcv(self.exchange, self.symbol)
            else:
                ohlcv = self.exchange.fetch_ohlcv(self.symbol)
        except Exception:
            return True

        if not ohlcv:
            return True

        # lazy import metrics to avoid circular import during test collection
        try:
            from api.routes.metrics import (
                aet_regime_total,
                aet_ml_veto_total,
                aet_orders_total,
                aet_orders_last_min,
                aet_consec_loss,
                aet_volatility_anomaly_total,
            )
        except Exception:
            aet_regime_total = None
            aet_ml_veto_total = None
            aet_orders_total = None
            aet_orders_last_min = None
            aet_consec_loss = None
            aet_volatility_anomaly_total = None

        # Strategy Selector (Phase 4)
        try:
            highs = [row[2] for row in ohlcv]
            lows = [row[3] for row in ohlcv]
            closes = [row[4] for row in ohlcv]

            sel = self.strategy_selector.select(highs, lows, closes)
            self.last_regime = sel["regime"]

            # metric: regime distribution
            try:
                if aet_regime_total is not None:
                    aet_regime_total.labels(symbol=self.symbol, regime=str(self.last_regime)).inc()
            except Exception:
                pass

            s3 = sel["strategy_output"]
            self.last_intent = s3["intent"]
            self.last_strength = s3["strength"]
            self.last_stop = s3["stop"]
            self.last_entry_price = s3["entry_price"]
            self.last_exit_price = s3["exit_price"]
            self.last_strategy_meta = s3["meta"]
            try:
                if getattr(self, "state", None) is not None:
                    self.state.last_regime = self.last_regime
            except Exception:
                pass

        except Exception:
            pass

        # --------------------------------------------------
        # ML META-SIGNAL RANKER (Hybrid Mode)
        # --------------------------------------------------
        try:
            meta = self.last_strategy_meta if isinstance(self.last_strategy_meta, dict) else {}
            ml_features = self._ml_extractor.extract(
                {
                    "signal_strength": self.last_strength,
                    "regime": self.last_regime,
                    "volatility": meta.get("volatility"),
                    "donchian": meta.get("donchian"),
                    "ma": meta.get("ma"),
                    "rsi": meta.get("rsi"),
                    "intent_veto": meta.get("intent_veto") or meta.get("intent"),
                }
            )

            ml_score = self._ml_ranker.score(ml_features)
        except Exception as e:
            try:
                logger.error(f"ExecutionEngine: ML scoring failed: {e}", **log_extra(symbol=self.symbol, cid=cid))
            except Exception:
                logger.error(f"ExecutionEngine: ML scoring failed: {e}")
            ml_score = 0.5

        ml_meta = {
            "ml_score": ml_score,
            "ml_effective_size": None,
            "ml_action": "pending",
            "ml_veto": False,
        }

        # volatility anomaly metric if engine provided a spike flag
        try:
            if isinstance(meta, dict) and meta.get("volatility_spike"):
                try:
                    if aet_volatility_anomaly_total is not None:
                        aet_volatility_anomaly_total.labels(symbol=self.symbol).inc()
                except Exception:
                    pass
                # notify ops about volatility anomaly (best-effort)
                try:
                    get_notifier().send("volatility_anomaly", symbol=self.symbol, msg="Unusual volatility detected", cid=cid)
                except Exception:
                    pass
                try:
                    if getattr(self, "state", None) is not None:
                        self.state.volatility_anomaly = True
                except Exception:
                    pass
        except Exception:
            pass

        # ------------------------------------------------------------
        # Phase 4.B – Execution Router (S3 intent → order directive)
        # ------------------------------------------------------------
        try:
            price = float(closes[-1]) if closes else 0.0

            # ------------------------------------------------------------
            # Phase 6.E-2 — update MAE/MFE trackers (high/low)
            # ------------------------------------------------------------
            try:
                if self.insight_enabled and getattr(self, "insight", None) is not None:
                    last_price = Decimal(str(price))
                    for tid, t in list(self._trade_trackers.items()):
                        try:
                            if last_price > t.get("high", Decimal("0")):
                                t["high"] = last_price
                            if last_price < t.get("low", Decimal("0")):
                                t["low"] = last_price
                        except Exception:
                            continue
            except Exception:
                pass
            # Phase 6: minimal risk hook (non intrusive).
            # Compute risk placeholders; this must not change behavior.
            try:
                try:
                    acct = self.exchange.account_overview()
                    positions = {
                        p.get("symbol"): Decimal(str(p.get("qty", "0")))
                        for p in acct.get("positions", [])
                        if isinstance(p, dict) and p.get("symbol")
                    }
                except Exception:
                    positions = {}

                prices_dec = [Decimal(str(c)) for c in closes[-20:]] if closes else []
                if getattr(self, "risk_v3", None) is not None:
                    try:
                        risk_info = self.risk_v3.apply(
                            self.symbol,
                            self.last_intent,
                            prices_dec,
                            positions,
                        )
                    except Exception:
                        risk_info = None
                else:
                    risk_info = None
            except Exception:
                risk_info = None

            qty = self._compute_position_size(
                signal=self.last_intent,
                ohlcv=ohlcv,
                equity=self.current_equity,
                price=price,
                regime=self.last_regime,
            )

            directive = self.execution_router.route(
                intent=self.last_intent,
                qty=qty,
                entry_price=self.last_entry_price,
                stop=self.last_stop,
                strength=self.last_strength,
            )

            # --------------------------------------------------
            # Apply ML hybrid gate AFTER risk sizing
            # --------------------------------------------------
            try:
                ml_veto_threshold = float(os.getenv("ML_VETO_THRESHOLD", "0.30"))
                ml_down_low = float(os.getenv("ML_DOWNSCALE_L", "0.50"))
                ml_down_high = float(os.getenv("ML_DOWNSCALE_H", "0.75"))

                new_size, veto_flag, ml_action = apply_ml_gate(
                    ml_meta["ml_score"],
                    qty,
                    ml_veto_threshold,
                    ml_down_low,
                    ml_down_high,
                )

                ml_meta["ml_effective_size"] = new_size
                ml_meta["ml_action"] = ml_action
                ml_meta["ml_veto"] = veto_flag

                # Telemetry
                self.last_ml_score = ml_meta["ml_score"]
                self.last_ml_action = ml_meta["ml_action"]
                self.last_ml_effective_size = str(ml_meta["ml_effective_size"])

                # If veto, replace directive with HOLD
                if veto_flag:
                    directive["action"] = "hold"
                    directive["qty"] = Decimal("0")
                    # metric: ML veto
                    try:
                        if aet_ml_veto_total is not None:
                            aet_ml_veto_total.labels(symbol=self.symbol, reason="ml_gate").inc()
                    except Exception:
                        pass
                    # notify ops about ml veto spike (best-effort)
                    try:
                        if float(ml_meta.get("ml_score", 0.0)) > 0.8:
                            get_notifier().send("ml_veto_spike", symbol=self.symbol, prob=float(ml_meta.get("ml_score", 0.0)), cid=cid)
                    except Exception:
                        pass
                    try:
                        if getattr(self, "state", None) is not None and float(ml_meta.get("ml_score", 0.0)) > 0.8:
                            self.state.ml_veto_spikes = int(getattr(self.state, "ml_veto_spikes", 0)) + 1
                    except Exception:
                        pass
                else:
                    directive["qty"] = new_size
            except Exception:
                # best-effort; do not break execution path
                pass

            self.last_router_directive = directive
        except Exception:
            self.last_router_directive = {
                "action": "hold",
                "side": None,
                "qty": Decimal("0"),
                "entry_price": Decimal("0"),
                "stop": Decimal("0"),
                "source": "router_v2",
                "meta": {"error": "router_failed"},
            }

        # ------------------------------------------------------------
        # Phase 4.B-3 – Paper Execution Simulation
        # ------------------------------------------------------------
        try:
            exec_state = self.paper_executor.execute(
                directive=self.last_router_directive,
                price=Decimal(str(price)),
            )

            # ------------------------------------------------------------
            # Phase 6.E-2 — Insight Engine: detect opens/closes (best-effort)
            # ------------------------------------------------------------
            try:
                if self.insight_enabled and getattr(self, "insight", None) is not None:
                    prev = dict(self.last_execution_state or {})
                    prev_side = prev.get("side")
                    try:
                        prev_qty = Decimal(str(prev.get("qty", "0")))
                    except Exception:
                        prev_qty = Decimal("0")

                    curr_side = exec_state.get("side")
                    try:
                        curr_qty = Decimal(str(exec_state.get("qty", "0")))
                    except Exception:
                        curr_qty = Decimal("0")

                    price_dec = Decimal(str(price))

                    # Close detected
                    if prev_side and (not curr_side or curr_qty == 0):
                        try:
                            tid = self._current_trade_id
                            tracker = self._trade_trackers.pop(tid, None) if tid else None
                            if tracker:
                                try:
                                    self.insight.record_trade(
                                        tid,
                                        entry_price=tracker.get("entry"),
                                        high=tracker.get("high"),
                                        low=tracker.get("low"),
                                        exit_price=price_dec,
                                        strategy=tracker.get("strategy"),
                                        regime=tracker.get("regime"),
                                    )
                                except Exception:
                                    pass
                            self._current_trade_id = None
                        except Exception:
                            pass

                    # Flip or new open
                    if (not prev_side or prev_qty == 0) and curr_side and curr_qty > 0:
                        # open new trade
                        try:
                            tid = f"insight_{int(time.time() * 1000)}"
                            entry_p = Decimal(str(exec_state.get("entry_price", price)))
                            strategy = getattr(self, "last_strategy", None) or getattr(self, "last_intent", "unknown")
                            self._trade_trackers[tid] = {
                                "entry": entry_p,
                                "high": entry_p,
                                "low": entry_p,
                                "strategy": strategy,
                                "regime": self.last_regime or "unknown",
                            }
                            self._current_trade_id = tid
                        except Exception:
                            pass

                    # Flip (previous non-none and current non-none but different side)
                    if prev_side and curr_side and prev_side != curr_side:
                        # treat as close + open
                        try:
                            # close previous
                            tid = self._current_trade_id
                            tracker = self._trade_trackers.pop(tid, None) if tid else None
                            if tracker:
                                try:
                                    self.insight.record_trade(
                                        tid,
                                        entry_price=tracker.get("entry"),
                                        high=tracker.get("high"),
                                        low=tracker.get("low"),
                                        exit_price=price_dec,
                                        strategy=tracker.get("strategy"),
                                        regime=tracker.get("regime"),
                                    )
                                except Exception:
                                    pass
                            # open new
                            ntid = f"insight_{int(time.time() * 1000)}"
                            entry_p = Decimal(str(exec_state.get("entry_price", price)))
                            strategy = getattr(self, "last_strategy", None) or getattr(self, "last_intent", "unknown")
                            self._trade_trackers[ntid] = {
                                "entry": entry_p,
                                "high": entry_p,
                                "low": entry_p,
                                "strategy": strategy,
                                "regime": self.last_regime or "unknown",
                            }
                            self._current_trade_id = ntid
                        except Exception:
                            pass
            except Exception:
                pass

            # NEW: Update engine equity from paper executor
            self.update_equity_from_executor(exec_state)
            self.last_execution_state = exec_state

        except Exception:
            self.last_execution_state = {
                "side": None,
                "qty": 0.0,
                "entry_price": 0.0,
                "realized_pnl": 0.0,
                "unrealized_pnl": 0.0,
                "equity_now": 10000.0,
                "error": "paper_executor_failed",
            }

        # Tests patch this strategy
        try:
            decision = simple_moving_average_strategy(ohlcv)
        except Exception:
            decision = "hold"

        self.last_signal = str(decision).lower()
        try:
            if getattr(self, "state", None) is not None:
                self.state.last_signal = self.last_signal
        except Exception:
            pass

        # Mock trade insert
        if self.last_signal in ("buy", "sell"):
            side = self.last_signal.upper()
            price = float(ohlcv[-1][4])
            qty = 0.01
            trade_id = f"{side.lower()}_{int(time.time())}"

            try:
                self.db.insert_trade(
                    trade_id=trade_id,
                    symbol=self.symbol,
                    side=side,
                    price=price,
                    amount=qty,
                    status="FILLED",
                    is_mock=1,
                )
                # metric: orders counter
                try:
                    if aet_orders_total is not None:
                        aet_orders_total.labels(symbol=self.symbol, side=side.lower()).inc()
                except Exception:
                    pass
            except Exception:
                log_json(logger, "error", "trade_insert_failed", symbol=self.symbol, cid=cid)

        try:
            if getattr(self, "state", None) is not None:
                # position_size: try to read last directive qty
                try:
                    self.state.position_size = float(self.last_router_directive.get("qty", 0))
                except Exception:
                    pass
        except Exception:
            pass

        # Rolling orders/min gauge update (best-effort)
        try:
            fn = getattr(self, "_orders_last_60s", None)
            if fn and callable(fn) and aet_orders_last_min is not None:
                try:
                    c = fn()
                    aet_orders_last_min.labels(symbol=self.symbol).set(int(c))
                except Exception:
                    pass
        except Exception:
            pass

        return True

    # -------------------------------------------------------------------
    # Snapshots
    # -------------------------------------------------------------------
    def snapshot(self) -> dict:
        return {
            "symbol": self.symbol,
            "last_regime": self.last_regime,
            "last_signal": self.last_signal,
            "current_drawdown": float(self.current_drawdown),
            "intent": self.last_intent,
            "strength": float(self.last_strength),
            "stop": float(self.last_stop),
            "router_directive": self.last_router_directive,
            "execution": self.last_execution_state,
            "current_equity": float(self.current_equity),
            # ----------------------------------------------------
            # Phase 6.D-2 — Risk V3 telemetry for dashboard
            # ----------------------------------------------------
            "risk_v3": self._risk_v3_snapshot(),
            "insight": self.insight.snapshot() if getattr(self, "insight_enabled", False) and getattr(self, "insight", None) is not None else None,
        }

    def _risk_v3_snapshot(self) -> dict:
        try:
            if not getattr(self, "risk_v3", None):
                return {"enabled": False}

            snap = self.risk_v3.telemetry_snapshot()

            # Convert Decimals safely
            def _clean(v):
                from decimal import Decimal
                if isinstance(v, Decimal):
                    return float(v)
                if isinstance(v, dict):
                    return {k: _clean(x) for k, x in v.items()}
                return v

            return {
                "enabled": getattr(self, "risk_v3_enabled", False),
                "volatility": _clean(snap.get("volatility")),
                "portfolio_vol": _clean(snap.get("portfolio_vol")),
                "scaling_factor": _clean(snap.get("scaling_factor")),
                "total_exposure": _clean(snap.get("total_exposure")),
                "symbol_exposure": _clean(snap.get("symbol_exposure")),
                "global_cap": float(getattr(self.risk_v3, "global_cap", 0)),
                "symbol_cap": float(getattr(self.risk_v3, "symbol_cap", 0)),
            }
        except Exception:
            return {"enabled": False, "error": True}

    def account_snapshot(self) -> dict:
        try:
            acct = self.exchange.account_overview()
            return {
                "equity_now": acct.get("equity") or acct.get("equity_now"),
                "positions": acct.get("positions", []),
            }
        except Exception:
            return {"equity_now": None, "positions": []}

    # -------------------------------------------------------------------
    # Upgrade Hooks (Phase 4)
    # -------------------------------------------------------------------
    # === UPGRADE-HOOK: STRATEGY_SELECTOR_V2 ===
    # === UPGRADE-HOOK: ML_VETO_V2 ===
    # === UPGRADE-HOOK: BREAKER_V2 ===
    # === UPGRADE-HOOK: PANIC_BAND_V2 ===
    # === UPGRADE-HOOK: EXECUTION_ROUTER_V2 ===
    # === UPGRADE-HOOK: TELEMETRY_V2 ===

    # -------------------------------------------------------------------
    # NEW: Equity Synchronization for Orchestrator / Paper Executor
    # -------------------------------------------------------------------
    def update_equity_from_executor(self, exec_state: dict) -> None:
        """
        Takes the paper executor's returned state and updates engine internal equity
        and risk metrics.
        """
        try:
            eq = Decimal(str(exec_state.get("equity_now", "10000")))
        except Exception:
            eq = Decimal("10000")

        self.current_equity = eq
        self._update_drawdown_state(eq)
        self._update_loss_streak(eq)
        # publish consecutive losses gauge (best-effort)
        try:
            try:
                from api.routes.metrics import aet_consec_loss
            except Exception:
                aet_consec_loss = None
            if aet_consec_loss is not None:
                try:
                    aet_consec_loss.labels(symbol=self.symbol).set(int(self._loss_streak))
                except Exception:
                    pass
        except Exception:
            pass
        # update engine state counters for health API
        try:
            if getattr(self, "state", None) is not None:
                try:
                    self.state.consecutive_losses = int(self._loss_streak)
                except Exception:
                    pass
                try:
                    self.state.position_size = float(self.last_router_directive.get("qty", 0))
                except Exception:
                    pass
        except Exception:
            pass

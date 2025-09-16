import time
from dotenv import load_dotenv
from bot.exchange import Exchange
from db.db_manager import DBManager
from strategy.trade_logic import simple_moving_average_strategy
from utils.logger import get_logger

# Load .env variables for keys and secrets
load_dotenv()

# Initialize module-specific logger
logger = get_logger(__name__)

class ExecutionEngine:
    def __init__(self):
        # Initialize MEXC exchange wrapper
        self.exchange = Exchange()
        # Initialize database
        self.db = DBManager()
        # Default trading symbol
        self.symbol = 'BTC/USDT'

    def run_once(self, is_mock=True):
        """
        Runs one cycle of signal evaluation and order execution (mock/testing mode).
        """
        logger.info(f"📈 Evaluating signal for {self.symbol}...")

        # Fetch mock OHLCV data (candle data)
        ohlcv = self.exchange.fetch_ohlcv(self.symbol)
        if not ohlcv:
            logger.warning("⚠️ No OHLCV data received. Skipping this run.")
            return

        # Apply strategy to get signal
        signal = simple_moving_average_strategy(ohlcv)
        logger.info(f"📊 Strategy signal: {signal}")

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
        logger.info(f"🚀 Running LIVE execution for {symbol} (trade={trade})")

        # Get real candle data
        ohlcv = self.exchange.fetch_ohlcv(symbol, use_live=True)
        if not ohlcv:
            logger.warning("⚠️ Failed to fetch live OHLCV data.")
            return

        # Get signal (buy/sell/hold)
        signal = simple_moving_average_strategy(ohlcv)
        logger.info(f"📊 Live strategy signal for {symbol}: {signal.upper()}")

        if signal in ["buy", "sell"]:
            if trade:
                if signal == "buy":
                    quote_amount = 10.0  # Spend 10 USDT
                    self.exchange.place_market_order(symbol, "buy", quote_amount)
                    logger.info(f"✅ Executed live BUY order for {symbol} (Amount: {quote_amount} USDT)")
                else:  # sell
                    quantity = 0.001  # Sell 0.001 BTC
                    self.exchange.place_market_order(symbol, "sell", quantity)
                    logger.info(f"✅ Executed live SELL order for {symbol} (Qty: {quantity} BTC)")
            else:
                logger.info("🟡 Trade signal received but live trading is DISABLED.")
        else:
            logger.info("🟡 No trade signal. Holding position.")

    def close(self):
        """
        Close database connection and clean up.
        """
        self.db.close()
        logger.info("✅ Resources released cleanly.")

import random
from utils.logger import get_logger

# Initialize logger for this module
logger = get_logger(__name__)

class TradeLogic:
    """
    Basic trade strategy logic. Will be replaced with smarter logic later.
    """

    def __init__(self, mode="random"):
        self.mode = mode
        logger.info(f"TradeLogic initialized in '{mode}' mode.")

    def generate_signal(self, symbol: str) -> dict:
        """
        Generate a random signal for the given symbol.
        Used in early-stage testing when no technical logic is implemented.
        """
        if self.mode == "random":
            action = random.choice(['buy', 'sell', 'hold'])
            confidence = round(random.uniform(0.4, 1.0), 2)
        else:
            action = 'hold'
            confidence = 0.0

        logger.info(f"[Signal Generated] {symbol} → Action: {action}, Confidence: {confidence}")

        return {
            "symbol": symbol,
            "action": action,
            "confidence": confidence
        }


def simple_moving_average_strategy(ohlcv):
    """
    A simple strategy based on 3-candle and 5-candle moving averages.
    Returns one of: 'buy', 'sell', or 'hold'
    """

    if len(ohlcv) < 5:
        logger.warning("Insufficient OHLCV data for SMA strategy. Returning 'hold'.")
        return 'hold'

    closes = [candle[4] for candle in ohlcv]  # Extract closing prices
    sma_3 = sum(closes[-3:]) / 3
    sma_5 = sum(closes[-5:]) / 5

    signal = 'hold'
    if sma_3 > sma_5:
        signal = 'buy'
    elif sma_3 < sma_5:
        signal = 'sell'

    logger.info(f"[SMA Strategy] SMA-3: {sma_3:.2f}, SMA-5: {sma_5:.2f} → Signal: {signal}")
    return signal


# Test logic from command line (optional)
if __name__ == "__main__":
    logic = TradeLogic()
    for _ in range(5):
        signal = logic.generate_signal("BTC/USDT")
        print(signal)

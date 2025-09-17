# run_live.py

import argparse
from core.execution_engine import ExecutionEngine

def main():
    parser = argparse.ArgumentParser(description="Run Caelus Live Strategy Execution")
    parser.add_argument(
        "--symbol",
        type=str,
        default="BTCUSDT",
        help="Trading symbol (default: BTCUSDT)"
    )
    parser.add_argument(
        "--trade",
        action="store_true",
        help="Execute trade if signal is BUY or SELL"
    )

    args = parser.parse_args()

    engine = ExecutionEngine()
    try:
        engine.run_live(symbol=args.symbol, trade=args.trade)
    finally:
        engine.close()

if __name__ == "__main__":
    main()

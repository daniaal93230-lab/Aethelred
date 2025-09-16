from bot.exchange import Exchange

def test_live_ohlcv():
    exchange = Exchange()
    symbol = "BTCUSDT"  # MEXC uses no slash in pair
    print(f"Fetching live OHLCV for {symbol}...\n")

    try:
        ohlcv = exchange.fetch_ohlcv(symbol, use_live=True)
        if not ohlcv:
            print("No data returned. Check logs for errors.")
            return

        for candle in ohlcv[:5]:  # Show only first 5 candles
            ts, o, h, l, c, v = candle
            print(f"Time: {ts}, Open: {o}, High: {h}, Low: {l}, Close: {c}, Volume: {v}")

    except Exception as e:
        print(f"❌ Error during live OHLCV fetch: {e}")

if __name__ == "__main__":
    test_live_ohlcv()

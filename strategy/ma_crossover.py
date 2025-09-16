import pandas as pd

def moving_average_crossover(data, short_window=10, long_window=50):
    """
    Simple moving average crossover strategy.
    data = DataFrame with 'close' prices
    """
    df = data.copy()
    df['SMA_short'] = df['close'].rolling(window=short_window).mean()
    df['SMA_long'] = df['close'].rolling(window=long_window).mean()

    # Signals
    df['signal'] = 0
    df.loc[df['SMA_short'] > df['SMA_long'], 'signal'] = 1   # Buy
    df.loc[df['SMA_short'] < df['SMA_long'], 'signal'] = -1  # Sell

    return df

try:
    from core.news_sentiment import *  # re-export
except ImportError:
    def score(symbol: str):
        return 0.0

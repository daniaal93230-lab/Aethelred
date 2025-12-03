"""
Batch 9 — Sentiment Provider (DI)

Sentiment is optional. Returns a multiplier in [0.5, 1.5].
Used by engine to adjust signal strength.
"""

from core.runtime_state import read_news_multiplier
from typing import cast


def get_sentiment_multiplier() -> float:
    # runtime_state returns Any → cast to float for strict typing
    return cast(float, read_news_multiplier(default=1.0))

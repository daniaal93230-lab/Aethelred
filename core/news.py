from __future__ import annotations
from typing import List, Dict, Any, Iterable
import feedparser
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

analyzer = SentimentIntensityAnalyzer()

def fetch_rss(urls: Iterable[str], max_items: int = 50) -> List[Dict[str, Any]]:
    """
    Fetch a few headlines from RSS/Atom feeds.
    Returns list of dicts: {title, link, published, summary}
    """
    out: List[Dict[str, Any]] = []
    for u in urls:
        try:
            feed = feedparser.parse(u)
            for e in (feed.entries or [])[:max_items]:
                out.append({
                    "title": getattr(e, "title", ""),
                    "link": getattr(e, "link", ""),
                    "published": getattr(e, "published", "") or getattr(e, "updated", ""),
                    "summary": getattr(e, "summary", ""),
                    "source": getattr(feed, "feed", {}).get("title", ""),
                })
        except Exception:
            continue
    return out

def filter_news(items: List[Dict[str, Any]], include_kw: Iterable[str] = (), exclude_kw: Iterable[str] = ()) -> List[Dict[str, Any]]:
    inc = [k.lower() for k in include_kw]
    exc = [k.lower() for k in exclude_kw]
    def ok(txt: str) -> bool:
        t = (txt or "").lower()
        if inc and not any(k in t for k in inc): return False
        if exc and any(k in t for k in exc): return False
        return True
    out = []
    for it in items:
        text = f"{it.get('title','')} {it.get('summary','')}"
        if ok(text):
            out.append(it)
    return out

def score_sentiment(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Adds 'sent' (compound in [-1,1]) to each item.
    """
    out = []
    for it in items:
        text = f"{it.get('title','')} {it.get('summary','')}"
        sc = analyzer.polarity_scores(text).get("compound", 0.0)
        it2 = dict(it)
        it2["sent"] = float(sc)
        out.append(it2)
    return out

def risk_modifier_from_news(items: List[Dict[str, Any]], window: int = 20) -> float:
    """
    Produce a crude scalar in [0.5, 1.5] from last `window` items:
      bearish => down-weight sizing (0.5..1.0)
      bullish => up-weight (1.0..1.5)
    Safe, bounded, and only used as a multiplier on position_size_usd.
    """
    if not items:
        return 1.0
    last = items[-window:]
    avg = sum(it.get("sent", 0.0) for it in last) / max(1, len(last))
    # map [-0.6..+0.6] roughly to [0.5..1.5], clamp
    x = 1.0 + max(-0.6, min(0.6, avg)) / 0.6 * 0.5
    return float(max(0.5, min(1.5, x)))

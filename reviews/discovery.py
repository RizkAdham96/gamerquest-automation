import json
from pathlib import Path

NEWS_FEED = Path("gamerquest-news-feed.json")
DEALS_FEED = Path("gamerquest-deals-feed.json")


def _load(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def discover_game_queries(news_feed=None, deals_feed=None, limit=3):
    news_feed = news_feed if news_feed is not None else _load(NEWS_FEED)
    deals_feed = deals_feed if deals_feed is not None else _load(DEALS_FEED)
    candidates = []

    for article in deals_feed.get("articles", []):
        game = str((article.get("deal") or {}).get("game", "")).strip()
        if game:
            candidates.append(game)

    for article in news_feed.get("articles", []):
        tags = article.get("tags") or []
        if tags:
            game = str(tags[0]).strip()
            if game:
                candidates.append(game)

    seen = set()
    result = []
    for value in candidates:
        key = " ".join(value.lower().split())
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
        if len(result) >= limit:
            break
    return result

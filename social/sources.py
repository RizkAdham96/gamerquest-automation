import json
from pathlib import Path

NEWS_FEED_FILE = Path("gamerquest-news-feed.json")
DEALS_FEED_FILE = Path("gamerquest-deals-feed.json")


def load_json_file(path):
    if not path.exists():
        return []

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            for key in ("articles", "items", "posts", "deals"):
                value = data.get(key)
                if isinstance(value, list):
                    return value

        return []

    except (json.JSONDecodeError, OSError):
        return []


def load_news():
    return load_json_file(NEWS_FEED_FILE)


def load_deals():
    return load_json_file(DEALS_FEED_FILE)


def get_all_content():
    content = []

    for article in load_news():
        if isinstance(article, dict):
            item = article.copy()
            item["source_type"] = "news"
            content.append(item)

    for deal in load_deals():
        if isinstance(deal, dict):
            item = deal.copy()
            item["source_type"] = "deal"
            content.append(item)

    return content

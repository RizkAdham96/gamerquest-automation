import json
from pathlib import Path

from platform_classifier import classify_platforms, merge_platform_tags

NEWS_FEED_FILE = Path("gamerquest-news-feed.json")


def article_text(article):
    seo = article.get("seo") or {}
    parts = [
        article.get("title", ""),
        article.get("excerpt", ""),
        article.get("content", ""),
        " ".join(article.get("tags") or []),
        seo.get("primary_keyword", ""),
        " ".join(seo.get("secondary_keywords") or []),
    ]
    return " ".join(str(part or "") for part in parts)


def enrich_article(article):
    result = dict(article)
    platforms = classify_platforms(article_text(article))
    result["platforms"] = platforms
    result["tags"] = merge_platform_tags(
        article.get("tags") or [],
        platforms,
    )
    return result


def enrich_feed(feed):
    result = dict(feed)
    articles = feed.get("articles") or []
    result["articles"] = [
        enrich_article(article)
        for article in articles
    ]
    result["count"] = len(result["articles"])
    return result


def main():
    if not NEWS_FEED_FILE.exists():
        print(
            "Platform enrichment skipped: "
            "gamerquest-news-feed.json is missing."
        )
        return

    feed = json.loads(
        NEWS_FEED_FILE.read_text(encoding="utf-8")
    )
    enriched = enrich_feed(feed)

    NEWS_FEED_FILE.write_text(
        json.dumps(
            enriched,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    counts = {
        "Nintendo": 0,
        "PlayStation": 0,
        "Xbox": 0,
    }

    for article in enriched["articles"]:
        for platform in article.get("platforms", []):
            counts[platform] = counts.get(platform, 0) + 1

    print(
        "Platform enrichment complete: "
        + ", ".join(
            f"{name}={count}"
            for name, count in counts.items()
        )
    )


if __name__ == "__main__":
    main()

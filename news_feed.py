import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


NEWS_FEED_FILE = Path(
    "gamerquest-news-feed.json"
)

MAX_FEED_ARTICLES = 50


def get_news_source_id(source_url):
    """
    Create a stable ID for one news source URL.
    """

    normalized = (
        str(source_url)
        .strip()
        .lower()
    )

    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


def parse_tags(tags):
    """
    Convert Groq's comma-separated tag string
    into a clean JSON list.
    """

    if isinstance(tags, list):
        return [
            str(tag).strip()
            for tag in tags
            if str(tag).strip()
        ]

    return [
        tag.strip()
        for tag in str(tags).split(",")
        if tag.strip()
    ]


def load_existing_feed():
    if not NEWS_FEED_FILE.exists():
        return {
            "generated_at": None,
            "count": 0,
            "articles": [],
        }

    try:
        data = json.loads(
            NEWS_FEED_FILE.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(data, dict):
            raise ValueError(
                "Feed is not a JSON object."
            )

        if not isinstance(
            data.get("articles"),
            list,
        ):
            raise ValueError(
                "Feed articles is not a list."
            )

        return data

    except Exception:
        return {
            "generated_at": None,
            "count": 0,
            "articles": [],
        }


def build_news_article(
    article_data,
    story,
):
    (
        seo_title,
        meta_description,
        primary_keyword,
        secondary_keywords,
        search_intent,
        suggested_slug,
        title,
        excerpt,
        category,
        tags,
        content,
    ) = article_data

    source_url = (
        story.get("url", "")
        .strip()
    )

    source_id = get_news_source_id(
        source_url
    )

    return {
        "source_id": source_id,

        "title": title,

        "excerpt": excerpt,

        "content": content,

        "slug": suggested_slug,

        "category": category,

        "tags": parse_tags(tags),

        "seo": {
            "seo_title": seo_title,
            "meta_description":
                meta_description,
            "primary_keyword":
                primary_keyword,
            "secondary_keywords":
                parse_tags(
                    secondary_keywords
                ),
            "search_intent":
                search_intent,
        },

        "source": {
            "url": source_url,
            "title": story.get(
                "title",
                "",
            ),
            "published_date":
                story.get(
                    "published_date",
                    "",
                ),
        },

        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),

        # We add this in Feature 2.
        "featured_image": None,
    }


def save_news_to_feed(
    article_data,
    story,
):
    new_article = build_news_article(
        article_data,
        story,
    )

    feed = load_existing_feed()

    existing_articles = (
        feed.get(
            "articles",
            [],
        )
    )

    # Remove old copy of the same source.
    existing_articles = [
        article
        for article in existing_articles
        if article.get(
            "source_id"
        )
        != new_article[
            "source_id"
        ]
    ]

    # Newest first.
    articles = [
        new_article,
        *existing_articles,
    ]

    articles = articles[
        :MAX_FEED_ARTICLES
    ]

    new_feed = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "count": len(articles),

        "articles": articles,
    }

    NEWS_FEED_FILE.write_text(
        json.dumps(
            new_feed,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("")
    print(
        "==================================="
    )
    print(
        "NEWS FEED UPDATED"
    )
    print(
        "==================================="
    )

    print(
        f"Feed articles: "
        f"{len(articles)}"
    )

    print(
        f"Added: "
        f"{new_article['title']}"
    )

    print(
        f"Feed file: "
        f"{NEWS_FEED_FILE}"
    )

    return new_article

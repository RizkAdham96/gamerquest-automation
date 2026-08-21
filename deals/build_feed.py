import json
from datetime import datetime, timezone
from pathlib import Path

from deals.aggregator import (
    collect_all_deals,
    get_deal_key,
)
from deals.article_generator import (
    generate_deal_article,
)


OUTPUT_FILE = Path(
    "gamerquest-deals-feed.json"
)


def build_feed():
    print("=" * 70)
    print("GamerQuest Deals Feed Builder")
    print("=" * 70)

    deals = collect_all_deals()

    articles = []

    for deal in deals:
        source_id = get_deal_key(deal)

        article = generate_deal_article(
            deal,
            source_id,
        )

        articles.append(article)

    feed = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "count": len(articles),
        "articles": articles,
    }

    OUTPUT_FILE.write_text(
        json.dumps(
            feed,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print(
        f"Articles written to feed: "
        f"{len(articles)}"
    )

    for article in articles:
        print(
            f"- {article['title']}"
        )

    print()
    print(
        f"Feed saved to: "
        f"{OUTPUT_FILE}"
    )


if __name__ == "__main__":
    build_feed()

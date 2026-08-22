import json
from datetime import datetime, timezone
from pathlib import Path

from deals.aggregator import collect_all_deals, get_deal_key
from deals.article_generator import generate_deal_article
from deals.image_generator import generate_deal_image

OUTPUT_FILE = Path("gamerquest-deals-feed.json")
IMAGES_DIR = Path("generated_images")
RAW_IMAGE_BASE = (
    "https://raw.githubusercontent.com/"
    "RizkAdham96/gamerquest-automation/main/generated_images"
)

def build_image_metadata(deal, source_id):
    filename = f"{source_id}.jpg"
    path = IMAGES_DIR / filename
    generate_deal_image(deal=deal, output_path=path)

    current_price = float(deal.get("current_price", 0))
    discount = int(deal.get("discount_percent", 0))
    offer_label = "gratuit" if current_price == 0 else f"-{discount}%"

    title = deal.get("title", "Jeu vidéo")
    store = deal.get("store", "boutique")

    return {
        "url": f"{RAW_IMAGE_BASE}/{filename}",
        "filename": filename,
        "alt": f"{title} {offer_label} sur {store} - GamerQuest",
        "caption": f"{title} : offre {offer_label} sur {store}.",
        "description": (
            f"Image GamerQuest générée automatiquement pour "
            f"l'offre {title} sur {store}."
        ),
    }

def build_feed():
    print("=" * 70)
    print("GamerQuest Deals Feed Builder")
    print("=" * 70)

    deals = collect_all_deals()
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    articles = []

    for deal in deals:
        source_id = get_deal_key(deal)
        article = generate_deal_article(deal, source_id)

        try:
            article["featured_image"] = build_image_metadata(deal, source_id)
            print(f"Image generated: {article['featured_image']['filename']}")
        except Exception as exc:
            print(f"WARNING: image generation failed for {deal.get('title')}: {exc}")
            article["featured_image"] = None

        articles.append(article)

    feed = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(articles),
        "articles": articles,
    }

    OUTPUT_FILE.write_text(
        json.dumps(feed, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print()
    print(f"Articles written to feed: {len(articles)}")
    for article in articles:
        print(f"- {article['title']}")
    print()
    print(f"Feed saved to: {OUTPUT_FILE}")

if __name__ == "__main__":
    build_feed()

import importlib


def article(title, slug, content=""):
    return {
        "title": title,
        "slug": slug,
        "content": content,
        "seo": {"primary_keyword": title},
        "tags": [],
    }


def test_news_quality_module_exposes_duplicate_guard():
    quality = importlib.import_module("news_quality")
    existing = [article(
        "Final Fantasy VII Revelation : date de sortie en 2027",
        "final-fantasy-vii-revelation-date-sortie-2027",
    )]
    candidate = article(
        "Final Fantasy 7 Revelation : sortie et plateformes en 2027",
        "final-fantasy-7-revelation-sortie-plateformes-2027",
    )
    assert quality.is_duplicate_news_topic(candidate, existing)


def test_news_quality_module_exposes_source_guard():
    quality = importlib.import_module("news_quality")
    story = {
        "title": "Toutes les annonces du State of Play de septembre 2026",
        "url": "https://example.com/state-of-play-septembre-2026",
    }
    assert not quality.source_image_matches_article(
        "Final Fantasy VII Revelation : date de sortie",
        story,
        "https://example.com/images/state-of-play-key-art.jpg",
    )

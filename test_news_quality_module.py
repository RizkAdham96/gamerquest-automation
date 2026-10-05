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


def test_self_promotional_unknown_sources_are_rejected():
    quality = importlib.import_module("news_quality")
    assert quality.is_self_promotional_source(
        "https://thegamearchives.com/2026/09/14/updates-from-thegamearchives",
        "Updates from TheGameArchives: A Complete Guide to Gaming News, "
        "Patches, and Releases - Thegamearchives",
    )
    # A site-name suffix alone is how ordinary headlines are formatted.
    assert not quality.is_self_promotional_source(
        "https://smallgamingblog.com/2026/10/hades-ii-patch",
        "Hades II patch 1.2 adds a new weapon - SmallGamingBlog",
    )
    # Trusted outlets are never judged by this rule.
    assert not quality.is_self_promotional_source(
        "https://www.eurogamer.net/eurogamer-readers-top-50-games",
        "Eurogamer readers' top 50 games",
    )

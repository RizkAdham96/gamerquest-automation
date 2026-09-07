import importlib
import os


os.environ.setdefault("GROQ_API_KEY", "test-key")
os.environ.setdefault("TAVILY_API_KEY", "test-key")
for proxy_variable in (
    "ALL_PROXY",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "all_proxy",
    "https_proxy",
    "http_proxy",
):
    os.environ.pop(proxy_variable, None)

automation = importlib.import_module("automation")


def article(title, slug, content=""):
    return {
        "title": title,
        "slug": slug,
        "content": content,
        "seo": {"primary_keyword": title},
        "tags": [],
    }


def test_same_story_from_a_different_source_is_a_duplicate():
    existing = [article(
        "Final Fantasy VII Revelation : date de sortie en 2027",
        "final-fantasy-vii-revelation-date-sortie-2027",
    )]
    candidate = article(
        "Final Fantasy 7 Revelation : sortie et plateformes en 2027",
        "final-fantasy-7-revelation-sortie-plateformes-2027",
    )

    assert automation.is_duplicate_news_topic(candidate, existing)


def test_different_story_about_same_game_is_not_a_duplicate():
    existing = [article(
        "The Witcher 3 Remastered : date de sortie annoncée",
        "witcher-3-remastered-date-sortie",
    )]
    candidate = article(
        "The Witcher 3 Remastered reçoit le DLC Songs of the Past",
        "witcher-3-remastered-dlc-songs-of-the-past",
    )

    assert not automation.is_duplicate_news_topic(candidate, existing)


def test_generic_roundup_image_is_rejected_for_game_specific_article():
    story = {
        "title": "Toutes les annonces du State of Play de septembre 2026",
        "url": "https://example.com/state-of-play-septembre-2026",
    }

    assert not automation.source_image_matches_article(
        "Final Fantasy VII Revelation : date de sortie",
        story,
        "https://example.com/images/state-of-play-key-art.jpg",
    )


def test_game_specific_source_image_is_kept():
    story = {
        "title": "Final Fantasy VII Revelation annoncé pour 2027",
        "url": "https://example.com/final-fantasy-vii-revelation",
    }

    assert automation.source_image_matches_article(
        "Final Fantasy VII Revelation : date de sortie",
        story,
        "https://example.com/images/final-fantasy-vii-revelation.jpg",
    )


def test_conflicting_release_year_for_same_topic_is_blocked():
    existing = [article(
        "Final Fantasy VII Revelation : date de sortie",
        "final-fantasy-vii-revelation-date-sortie",
        "La sortie est annoncée pour 2027 sur PS5.",
    )]
    candidate = article(
        "Final Fantasy 7 Revelation : date de sortie",
        "final-fantasy-7-revelation-date-sortie",
        "Le jeu sortira en 2026 sur PS5.",
    )

    assert automation.has_conflicting_news_claims(candidate, existing)


def test_matching_release_claims_do_not_conflict():
    existing = [article(
        "Final Fantasy VII Revelation : date de sortie",
        "final-fantasy-vii-revelation-date-sortie",
        "La sortie est annoncée pour 2027 sur PS5.",
    )]
    candidate = article(
        "Final Fantasy 7 Revelation : date de sortie",
        "final-fantasy-7-revelation-date-sortie",
        "Le jeu sortira en 2027 sur PS5.",
    )

    assert not automation.has_conflicting_news_claims(candidate, existing)


def test_exclusive_platform_claim_conflict_is_blocked():
    existing = [article(
        "Project Nova : plateformes confirmées",
        "project-nova-plateformes",
        "Project Nova sera une exclusivité PS5.",
    )]
    candidate = article(
        "Project Nova : plateformes confirmées",
        "project-nova-plateformes-confirmation",
        "Project Nova sortira sur Xbox Series et PC.",
    )

    assert automation.has_conflicting_news_claims(candidate, existing)


def test_duplicate_is_not_built_or_added_to_feed(monkeypatch, tmp_path):
    existing = article(
        "Final Fantasy VII Revelation : date de sortie en 2027",
        "final-fantasy-vii-revelation-date-sortie-2027",
    )
    monkeypatch.setattr(
        automation,
        "load_existing_news_feed",
        lambda: {"articles": [existing]},
    )
    monkeypatch.setattr(
        automation,
        "build_news_feed_article",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("duplicate article must not build an image")
        ),
    )
    monkeypatch.setattr(automation, "NEWS_FEED_FILE", tmp_path / "feed.json")
    article_data = (
        "SEO title", "meta", "keyword", "", "information",
        "final-fantasy-7-revelation-sortie-plateformes-2027",
        "Final Fantasy 7 Revelation : sortie et plateformes en 2027",
        "excerpt", "Actualites", "Final Fantasy",
        "Le jeu sortira en 2027 sur PS5.",
    )

    assert automation.save_news_to_feed(
        article_data,
        {"url": "https://different.example/story"},
    ) is None
    assert not (tmp_path / "feed.json").exists()

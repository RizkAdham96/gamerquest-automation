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


def test_news_discovery_includes_long_tail_player_intent():
    queries = " ".join(automation.SEARCH_QUERIES).lower()
    assert "guide" in queries
    assert "comment" in queries
    assert "probleme" in queries or "problème" in queries


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


def test_same_subject_with_overlapping_search_intent_is_duplicate():
    existing = [article(
        "Final Fantasy VII Revelation : date de sortie, plateformes, prix et DLC",
        "final-fantasy-vii-revelation-sortie-plateformes-prix-dlc",
    )]
    candidate = article(
        "Final Fantasy VII Revelation : prix, gameplay, plateformes et date de sortie",
        "final-fantasy-vii-revelation-prix-gameplay-plateformes-date",
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


def test_wo_long_reworded_article_is_a_duplicate():
    existing = [article(
        "Wo Long Complete Edition arrive sur Switch 2 : "
        "performance en deçà des rivaux",
        "wo-long-complete-edition-switch-2-performance",
    )]
    candidate = article(
        "Wo Long: Fallen Dynasty Complete Edition disponible sur "
        "Nintendo Switch 2 – tout ce qu’il faut savoir",
        "wo-long-fallen-dynasty-switch-2",
    )

    assert automation.is_duplicate_news_topic(candidate, existing)


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


def test_historical_topic_history_blocks_old_wordpress_duplicate(monkeypatch, tmp_path):
    history_file = tmp_path / "news_topic_history.json"
    history_file.write_text(
        '{"articles":[{"title":"Final Fantasy VII Revelation : date de sortie, plateformes, prix et DLC","slug":"final-fantasy-vii-revelation-sortie-plateformes-prix-dlc","content":"","seo":{"primary_keyword":"Final Fantasy VII Revelation date de sortie"},"tags":[]}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(automation, "NEWS_TOPIC_HISTORY_FILE", history_file)
    monkeypatch.setattr(
        automation,
        "load_existing_news_feed",
        lambda: {"articles": []},
    )
    candidate = (
        "Final Fantasy VII Revelation : prix, plateformes et date de sortie",
        "meta",
        "Final Fantasy VII Revelation date de sortie",
        "Final Fantasy VII Revelation plateformes",
        "Informational",
        "final-fantasy-vii-revelation-date-sortie-plateformes",
        "Final Fantasy VII Revelation : prix, plateformes et date de sortie",
        "excerpt",
        "Actualités",
        "Final Fantasy VII, Revelation",
        "Les informations de sortie et de plateformes sont détaillées.",
    )
    assert automation.news_quality_rejection(candidate)


def test_remember_news_topic_persists_new_topic(monkeypatch, tmp_path):
    history_file = tmp_path / "news_topic_history.json"
    monkeypatch.setattr(automation, "NEWS_TOPIC_HISTORY_FILE", history_file)
    item = article(
        "Project Nova : date de sortie",
        "project-nova-date-sortie",
    )
    automation.remember_news_topic(item)
    loaded = automation.load_news_topic_history()
    assert loaded[0]["slug"] == "project-nova-date-sortie"



def test_search_collects_fallback_candidates_even_when_first_search_has_results(monkeypatch):
    calls = []

    class FakeResponse:
        def __init__(self, number):
            self.number = number

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "results": [
                    {
                        "title": f"Fresh story {self.number}",
                        "url": f"https://example.com/story-{self.number}",
                        "content": "x" * 2000,
                        "published_date": "2026-09-18",
                    }
                ]
            }

    def fake_post(*args, **kwargs):
        calls.append(kwargs["json"]["query"])
        return FakeResponse(len(calls))

    monkeypatch.setattr(
        automation,
        "check_monthly_credit_safety",
        lambda: {"searches_used": 0},
    )
    monkeypatch.setattr(
        automation,
        "record_tavily_search",
        lambda state: state.__setitem__(
            "searches_used",
            state["searches_used"] + 1,
        ),
    )
    monkeypatch.setattr(
        automation.requests,
        "post",
        fake_post,
    )
    monkeypatch.setattr(
        automation,
        "source_already_used",
        lambda url: False,
    )
    monkeypatch.setattr(
        automation,
        "source_tier",
        lambda url: 2,
    )
    monkeypatch.setattr(
        automation,
        "result_content_length",
        lambda result: 2000,
    )

    results = automation.search_gaming_news()

    expected_searches = min(
        automation.MAX_TAVILY_SEARCHES_PER_RUN,
        len(automation.SEARCH_QUERIES),
    )
    assert len(calls) == expected_searches
    assert len(results) == expected_searches


def test_main_retries_next_candidate_after_source_validation_rejection(monkeypatch):
    stories = [
        {
            "title": "Bad candidate",
            "url": "https://example.com/bad",
        },
        {
            "title": "Good candidate",
            "url": "https://example.com/good",
        },
    ]
    saved = []

    article_data = (
        "SEO title",
        "meta",
        "keyword",
        "",
        "information",
        "good-candidate",
        "Good candidate",
        "excerpt",
        "Actualités",
        "Good Candidate",
        "Fresh article body.",
    )

    monkeypatch.setattr(
        automation,
        "search_gaming_news",
        lambda: list(stories),
    )
    monkeypatch.setattr(
        automation,
        "select_best_story",
        lambda results: results[0],
    )
    monkeypatch.setattr(
        automation,
        "find_matching_official_source",
        lambda selected, results: None,
    )
    monkeypatch.setattr(
        automation,
        "extract_page",
        lambda story: "source text " * 200,
    )
    monkeypatch.setattr(
        automation,
        "validate_source",
        lambda story, source_text: (
            (False, "bad source")
            if story["url"].endswith("/bad")
            else (True, "ok")
        ),
    )
    monkeypatch.setattr(
        automation,
        "save_rejection_report",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        automation.time,
        "sleep",
        lambda seconds: None,
    )
    monkeypatch.setattr(
        automation,
        "generate_article",
        lambda *args, **kwargs: "generated",
    )
    monkeypatch.setattr(
        automation,
        "parse_article",
        lambda generated: article_data,
    )
    monkeypatch.setattr(
        automation,
        "verify_and_correct_article",
        lambda data, source_text, official_text: data,
    )
    monkeypatch.setattr(
        automation,
        "news_quality_rejection",
        lambda data: "",
    )
    monkeypatch.setattr(
        automation,
        "add_contextual_internal_links",
        lambda data: data,
    )
    monkeypatch.setattr(
        automation,
        "save_draft",
        lambda data, story, official_story: saved.append(
            ("draft", story["url"])
        ),
    )
    monkeypatch.setattr(
        automation,
        "save_news_to_feed",
        lambda data, story, official_story: (
            saved.append(("feed", story["url"]))
            or {"slug": "good-candidate"}
        ),
    )

    automation.main()

    assert ("feed", "https://example.com/good") in saved
    assert ("feed", "https://example.com/bad") not in saved


def test_main_retries_next_candidate_after_quality_guard_rejection(monkeypatch):
    stories = [
        {
            "title": "Duplicate candidate",
            "url": "https://example.com/duplicate",
        },
        {
            "title": "Fresh candidate",
            "url": "https://example.com/fresh",
        },
    ]
    saved = []

    def article_for(url):
        duplicate = url.endswith("/duplicate")
        return (
            "SEO title",
            "meta",
            "keyword",
            "",
            "information",
            "duplicate" if duplicate else "fresh",
            "Duplicate candidate" if duplicate else "Fresh candidate",
            "excerpt",
            "Actualités",
            "Gaming",
            "Article body.",
        )

    monkeypatch.setattr(
        automation,
        "search_gaming_news",
        lambda: list(stories),
    )
    monkeypatch.setattr(
        automation,
        "select_best_story",
        lambda results: results[0],
    )
    monkeypatch.setattr(
        automation,
        "find_matching_official_source",
        lambda selected, results: None,
    )
    monkeypatch.setattr(
        automation,
        "extract_page",
        lambda story: "source text " * 200,
    )
    monkeypatch.setattr(
        automation,
        "validate_source",
        lambda story, source_text: (True, "ok"),
    )
    monkeypatch.setattr(
        automation.time,
        "sleep",
        lambda seconds: None,
    )
    monkeypatch.setattr(
        automation,
        "generate_article",
        lambda story, *args, **kwargs: story["url"],
    )
    monkeypatch.setattr(
        automation,
        "parse_article",
        article_for,
    )
    monkeypatch.setattr(
        automation,
        "verify_and_correct_article",
        lambda data, source_text, official_text: data,
    )
    monkeypatch.setattr(
        automation,
        "news_quality_rejection",
        lambda data: (
            "The same News story already exists in the feed."
            if data[5] == "duplicate"
            else ""
        ),
    )
    monkeypatch.setattr(
        automation,
        "save_rejection_report",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        automation,
        "add_contextual_internal_links",
        lambda data: data,
    )
    monkeypatch.setattr(
        automation,
        "save_draft",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        automation,
        "save_news_to_feed",
        lambda data, story, official_story: (
            saved.append(story["url"])
            or {"slug": data[5]}
        ),
    )

    automation.main()

    assert saved == ["https://example.com/fresh"]

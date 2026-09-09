from reviews.discovery import discover_game_queries
from reviews.pipeline import build_review_record, verdict_from_percent
from reviews.steam import choose_best_search_result
from reviews.wordpress import build_post_payload


def test_discovery_prefers_deals_then_news_and_deduplicates():
    deals = {"articles": [{"deal": {"game": "Alone With You"}}]}
    news = {"articles": [
        {"tags": ["Wo Long", "Switch 2"]},
        {"tags": ["Wo Long", "DLC"]},
        {"tags": ["Elden Ring", "PS5"]},
    ]}
    assert discover_game_queries(news, deals, limit=3) == [
        "Alone With You", "Wo Long", "Elden Ring"
    ]


def test_verdict_labels_are_transparent():
    assert verdict_from_percent(95) == "Exceptionnellement positif"
    assert verdict_from_percent(82) == "Très positif"
    assert verdict_from_percent(71) == "Positif"
    assert verdict_from_percent(55) == "Mitigé"


def test_build_review_record_uses_player_score_not_fake_editorial_score():
    app = {
        "steam_appid": 1448440,
        "name": "Wo Long: Fallen Dynasty",
        "header_image": "https://cdn.example/header.jpg",
        "short_description": "Action RPG sombre.",
        "developers": ["Team NINJA"],
        "genres": [{"description": "Action"}, {"description": "RPG"}],
        "release_date": {"date": "3 Mar, 2023"},
        "platforms": {"windows": True, "mac": False, "linux": False},
    }
    reviews = {"total_positive": 1000, "total_negative": 250, "total_reviews": 1250}
    record = build_review_record(app, reviews)
    assert record["score_5"] == 4.0
    assert record["positive_percent"] == 80
    assert record["score_label"] == "Très positif"
    assert record["image_url"] == "https://cdn.example/header.jpg"
    assert "Score joueurs GamerQuest" in record["content"]
    assert "1250" in record["content"]
    assert "Team NINJA" in record["content"]


def test_choose_best_search_result_prefers_exact_title():
    items = [
        {"id": 1, "name": "Wo Long Demo"},
        {"id": 2, "name": "Wo Long: Fallen Dynasty"},
    ]
    chosen = choose_best_search_result("Wo Long: Fallen Dynasty", items)
    assert chosen["id"] == 2


def test_wordpress_payload_targets_tests_category_and_featured_media():
    record = {
        "appid": 2,
        "name": "Game Name",
        "content": "<p>Body</p>",
        "excerpt": "Excerpt",
    }
    payload = build_post_payload(record, category_id=9, media_id=44)
    assert payload["status"] == "publish"
    assert payload["categories"] == [9]
    assert payload["featured_media"] == 44
    assert payload["slug"].startswith("avis-2-game-name")

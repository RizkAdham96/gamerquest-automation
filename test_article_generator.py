from deals.article_generator import (
    generate_deal_article,
)


def test_generates_free_game_article():
    deal = {
        "title": "Cardpocalypse Standard Edition",
        "store": "Epic Games Store",
        "original_price": 23.99,
        "current_price": 0,
        "discount_percent": 100,
        "url": "https://example.com/game",
        "expires_at": "2026-08-27T15:00:00.000Z",
    }

    article = generate_deal_article(
        deal,
        "test-id",
    )

    assert article["source_id"] == "test-id"

    assert (
        "gratuit"
        in article["title"].lower()
    )

    assert (
        "23,99 €"
        in article["content"]
    )

    assert (
        "27 août 2026"
        in article["content"]
    )

    assert (
        "https://example.com/game"
        in article["content"]
    )


def test_generates_90_percent_article():
    deal = {
        "title": "Example Game",
        "store": "Steam",
        "original_price": 59.99,
        "current_price": 5.99,
        "discount_percent": 90,
        "url": "https://example.com/deal",
    }

    article = generate_deal_article(
        deal,
        "deal-90",
    )

    assert "-90%" in article["title"]

    assert (
        "59,99 €"
        in article["content"]
    )

    assert (
        "5,99 €"
        in article["content"]
    )

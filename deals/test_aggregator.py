from deals.aggregator import (
    deduplicate_deals,
    get_deal_key,
    filter_new_deals,
)


def test_get_deal_key_is_stable():
    deal = {
        "title": "Cardpocalypse Standard Edition",
        "store": "Epic Games Store",
        "url": "https://store.epicgames.com/fr/p/cardpocalypse/home",
    }

    key1 = get_deal_key(deal)
    key2 = get_deal_key(deal)

    assert key1 == key2


def test_duplicate_deals_are_removed():
    deals = [
        {
            "title": "Cardpocalypse Standard Edition",
            "store": "Epic Games Store",
            "url": "https://store.epicgames.com/fr/p/cardpocalypse/home",
        },
        {
            "title": "Cardpocalypse Standard Edition",
            "store": "Epic Games Store",
            "url": "https://store.epicgames.com/fr/p/cardpocalypse/home",
        },
    ]

    result = deduplicate_deals(deals)

    assert len(result) == 1


def test_different_games_are_kept():
    deals = [
        {
            "title": "Game A",
            "store": "Steam",
            "url": "https://example.com/game-a",
        },
        {
            "title": "Game B",
            "store": "Epic Games Store",
            "url": "https://example.com/game-b",
        },
    ]

    result = deduplicate_deals(deals)

    assert len(result) == 2


def test_already_seen_deal_is_filtered():
    deal = {
        "title": "Cardpocalypse Standard Edition",
        "store": "Epic Games Store",
        "url": "https://store.epicgames.com/fr/p/cardpocalypse/home",
    }

    key = get_deal_key(deal)

    new_deals = filter_new_deals(
        [deal],
        {key},
    )

    assert new_deals == []


def test_unseen_deal_is_kept():
    deal = {
        "title": "Cardpocalypse Standard Edition",
        "store": "Epic Games Store",
        "url": "https://store.epicgames.com/fr/p/cardpocalypse/home",
    }

    new_deals = filter_new_deals(
        [deal],
        set(),
    )

    assert len(new_deals) == 1

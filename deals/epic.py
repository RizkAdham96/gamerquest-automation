import requests


EPIC_FREE_GAMES_URL = (
    "https://store-site-backend-static-ipv4.ak.epicgames.com/"
    "freeGamesPromotions"
)


def is_valid_epic_free_game(game):
    original_price = game.get("original_price", 0)
    current_price = game.get("current_price", 0)

    return original_price > 0 and current_price == 0


def fetch_epic_free_games():
    params = {
        "locale": "fr-FR",
        "country": "FR",
        "allowCountries": "FR",
    }

    response = requests.get(
        EPIC_FREE_GAMES_URL,
        params=params,
        timeout=30,
        headers={
            "User-Agent": "GamerQuestFR/1.0"
        },
    )

    response.raise_for_status()

    data = response.json()

    elements = (
        data
        .get("data", {})
        .get("Catalog", {})
        .get("searchStore", {})
        .get("elements", [])
    )

    free_games = []

    for item in elements:
        promotions = item.get("promotions")

        if not promotions:
            continue

        promotional_offers = promotions.get(
            "promotionalOffers", []
        )

        if not promotional_offers:
            continue

        offers = promotional_offers[0].get(
            "promotionalOffers", []
        )

        if not offers:
            continue

        offer = offers[0]

        discount_setting = offer.get(
            "discountSetting", {}
        )

        discount_percentage = discount_setting.get(
            "discountPercentage"
        )

        if discount_percentage != 0:
            continue

        price_info = (
            item
            .get("price", {})
            .get("totalPrice", {})
        )

        original_price_cents = price_info.get(
            "originalPrice", 0
        )

        original_price = original_price_cents / 100

        title = item.get(
            "title",
            "Unknown Epic Game",
        )

        slug = item.get("productSlug")

        if not slug:
            mappings = item.get(
                "catalogNs", {}
            ).get(
                "mappings", []
            )

            if mappings:
                slug = mappings[0].get(
                    "pageSlug"
                )

        if slug:
            url = (
                f"https://store.epicgames.com/fr/p/"
                f"{slug}"
            )
        else:
            url = (
                "https://store.epicgames.com/"
                "fr/free-games"
            )

        game = {
            "title": title,
            "store": "Epic Games Store",
            "original_price": original_price,
            "current_price": 0,
            "discount_percent": 100,
            "url": url,
            "starts_at": offer.get(
                "startDate"
            ),
            "expires_at": offer.get(
                "endDate"
            ),
        }

        if not is_valid_epic_free_game(game):
            continue

        free_games.append(game)

    return free_games

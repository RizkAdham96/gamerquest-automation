import requests

EPIC_FREE_GAMES_URL = (
    "https://store-site-backend-static-ipv4.ak.epicgames.com/"
    "freeGamesPromotions"
)

def is_valid_epic_free_game(game):
    return game.get("original_price", 0) > 0 and game.get("current_price", 0) == 0

def get_epic_artwork(item):
    key_images = item.get("keyImages", []) or []
    preferred_types = [
        "DieselStoreFrontWide",
        "OfferImageWide",
        "Featured",
        "DieselGameBoxWide",
        "VaultClosed",
        "Thumbnail",
    ]
    for preferred_type in preferred_types:
        for image in key_images:
            if image.get("type") == preferred_type and image.get("url"):
                return image["url"]
    for image in key_images:
        if image.get("url"):
            return image["url"]
    return None

def fetch_epic_free_games():
    response = requests.get(
        EPIC_FREE_GAMES_URL,
        params={"locale":"fr-FR","country":"FR","allowCountries":"FR"},
        timeout=30,
        headers={"User-Agent":"GamerQuestFR/1.0"},
    )
    response.raise_for_status()
    elements = (
        response.json().get("data",{}).get("Catalog",{})
        .get("searchStore",{}).get("elements",[])
    )
    free_games = []
    for item in elements:
        promotions = item.get("promotions")
        if not promotions:
            continue
        promotional_offers = promotions.get("promotionalOffers", [])
        if not promotional_offers:
            continue
        offers = promotional_offers[0].get("promotionalOffers", [])
        if not offers:
            continue
        offer = offers[0]
        if offer.get("discountSetting",{}).get("discountPercentage") != 0:
            continue
        price_info = item.get("price",{}).get("totalPrice",{})
        original_price = price_info.get("originalPrice",0) / 100
        title = item.get("title","Unknown Epic Game")
        slug = item.get("productSlug")
        if not slug:
            mappings = item.get("catalogNs",{}).get("mappings",[])
            if mappings:
                slug = mappings[0].get("pageSlug")
        url = (
            f"https://store.epicgames.com/fr/p/{slug}"
            if slug else
            "https://store.epicgames.com/fr/free-games"
        )
        game = {
            "title": title,
            "store": "Epic Games Store",
            "original_price": original_price,
            "current_price": 0,
            "discount_percent": 100,
            "url": url,
            "starts_at": offer.get("startDate"),
            "expires_at": offer.get("endDate"),
            "image_url": get_epic_artwork(item),
        }
        if is_valid_epic_free_game(game):
            free_games.append(game)
    return free_games

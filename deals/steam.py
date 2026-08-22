import requests


STEAM_FEATURED_URL = (
    "https://store.steampowered.com/api/featuredcategories/"
)


def fetch_steam_specials():
    response = requests.get(
        STEAM_FEATURED_URL,
        params={
            "cc": "FR",
            "l": "french",
        },
        timeout=20,
        headers={
            "User-Agent": "GamerQuestFR/1.0"
        },
    )

    response.raise_for_status()

    data = response.json()

    specials = (
        data
        .get("specials", {})
        .get("items", [])
    )

    deals = []

    for item in specials:
        app_id = item.get("id")

        discount = int(
            item.get(
                "discount_percent",
                0,
            )
            or 0
        )

        original_price = (
            item.get(
                "original_price",
                0,
            )
            or 0
        )

        final_price = (
            item.get(
                "final_price",
                0,
            )
            or 0
        )

        # Steam prices are returned in cents.
        original_price = (
            original_price / 100
        )

        final_price = (
            final_price / 100
        )

        image_url = (
            item.get(
                "large_capsule_image"
            )
            or item.get(
                "small_capsule_image"
            )
            or item.get(
                "header_image"
            )
        )

        # Reliable fallback using the Steam App ID.
        if not image_url and app_id:
            image_url = (
                "https://cdn.cloudflare.steamstatic.com/"
                f"steam/apps/{app_id}/header.jpg"
            )

        deal = {
            "appid": app_id,
            "title": item.get(
                "name",
                "Unknown",
            ),
            "store": "Steam",
            "original_price": original_price,
            "current_price": final_price,
            "discount_percent": discount,
            "url": (
                "https://store.steampowered.com/"
                f"app/{app_id}/"
            ),
            "image_url": image_url,
        }

        deals.append(deal)

    return deals

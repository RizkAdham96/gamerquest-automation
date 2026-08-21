import requests

STEAM_FEATURED_URL = "https://store.steampowered.com/api/featuredcategories/"


def fetch_steam_specials():
    response = requests.get(
        STEAM_FEATURED_URL,
        params={
            "cc": "FR",
            "l": "french",
        },
        timeout=20,
    )

    response.raise_for_status()
    data = response.json()

    specials = data.get("specials", {}).get("items", [])

    deals = []

    for item in specials:
        discount = int(item.get("discount_percent", 0) or 0)

        original_price = item.get("original_price", 0) or 0
        final_price = item.get("final_price", 0) or 0

        # Steam prices are returned in cents
        original_price = original_price / 100
        final_price = final_price / 100

        deal = {
            "appid": item.get("id"),
            "title": item.get("name", "Unknown"),
            "store": "Steam",
            "original_price": original_price,
            "current_price": final_price,
            "discount_percent": discount,
            "url": f"https://store.steampowered.com/app/{item.get('id')}/",
        }

        deals.append(deal)

    return deals

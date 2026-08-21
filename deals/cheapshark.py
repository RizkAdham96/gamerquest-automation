import requests


API_URL = "https://www.cheapshark.com/api/1.0/deals"

HEADERS = {
    "User-Agent": "GamerQuestFR/1.0"
}


def fetch_deals(page_size=60):
    params = {
        "pageSize": page_size,
        "onSale": "1",
        "sortBy": "Savings",
        "desc": "1",
    }

    response = requests.get(
        API_URL,
        params=params,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    raw_deals = response.json()

    deals = []

    for item in raw_deals:
        normal_price = float(item.get("normalPrice", 0) or 0)
        sale_price = float(item.get("salePrice", 0) or 0)
        savings = float(item.get("savings", 0) or 0)

        deal_id = item.get("dealID")

        deals.append(
            {
                "title": item.get("title", "Unknown"),
                "store": item.get("storeID"),
                "original_price": normal_price,
                "current_price": sale_price,
                "discount_percent": round(savings),
                "steam_app_id": item.get("steamAppID"),
                "deal_id": deal_id,
                "url": (
                    f"https://www.cheapshark.com/redirect?dealID={deal_id}"
                    if deal_id
                    else None
                ),
            }
        )

    return deals

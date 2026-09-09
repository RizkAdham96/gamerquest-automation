import requests

STORE_SEARCH = "https://store.steampowered.com/api/storesearch/"
APP_DETAILS = "https://store.steampowered.com/api/appdetails"
APP_REVIEWS = "https://store.steampowered.com/appreviews/{appid}"


def _norm(value):
    return " ".join(str(value or "").lower().replace(":", " ").split())


def choose_best_search_result(query, items):
    if not items:
        return None
    q = _norm(query)
    exact = [item for item in items if _norm(item.get("name")) == q]
    if exact:
        return exact[0]
    starts = [item for item in items if _norm(item.get("name")).startswith(q)]
    return starts[0] if starts else items[0]


def search_game(query, session=requests):
    response = session.get(
        STORE_SEARCH,
        params={"term": query, "l": "french", "cc": "FR"},
        timeout=45,
    )
    response.raise_for_status()
    return choose_best_search_result(query, response.json().get("items") or [])


def fetch_app_details(appid, session=requests):
    response = session.get(
        APP_DETAILS,
        params={"appids": int(appid), "l": "french", "cc": "FR"},
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json().get(str(appid)) or {}
    if not payload.get("success"):
        return None
    data = payload.get("data") or {}
    data["steam_appid"] = int(appid)
    return data


def fetch_review_summary(appid, session=requests):
    response = session.get(
        APP_REVIEWS.format(appid=int(appid)),
        params={"json": 1, "language": "all", "purchase_type": "all", "num_per_page": 0},
        timeout=45,
    )
    response.raise_for_status()
    summary = response.json().get("query_summary") or {}
    return {
        "total_positive": int(summary.get("total_positive") or 0),
        "total_negative": int(summary.get("total_negative") or 0),
        "total_reviews": int(summary.get("total_reviews") or 0),
    }

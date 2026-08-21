import hashlib
import json
from pathlib import Path

from deals.cheapshark import fetch_deals as fetch_cheapshark_deals
from deals.epic import fetch_epic_free_games
from deals.filter import should_accept_deal
from deals.steam import fetch_steam_specials


STATE_FILE = Path("state/deals_seen.json")


def get_deal_key(deal):
    """
    Generate a stable unique identifier for a deal.
    """

    title = str(deal.get("title", "")).strip().lower()
    store = str(deal.get("store", "")).strip().lower()
    url = str(deal.get("url", "")).strip().lower()

    raw_key = f"{store}|{title}|{url}"

    return hashlib.sha256(
        raw_key.encode("utf-8")
    ).hexdigest()


def deduplicate_deals(deals):
    """
    Remove duplicate deals from the current scan.
    """

    unique_deals = []
    seen = set()

    for deal in deals:
        key = get_deal_key(deal)

        if key in seen:
            continue

        seen.add(key)
        unique_deals.append(deal)

    return unique_deals


def load_seen_deals():
    """
    Load deal IDs previously processed by GamerQuest.
    """

    if not STATE_FILE.exists():
        return set()

    try:
        with STATE_FILE.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        return set(data)

    except (json.JSONDecodeError, OSError):
        return set()


def save_seen_deals(keys):
    """
    Save processed deal IDs.
    """

    STATE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with STATE_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            sorted(keys),
            file,
            indent=2,
            ensure_ascii=False,
        )


def filter_new_deals(deals, seen_keys):
    """
    Keep only deals GamerQuest has never processed.
    """

    return [
        deal
        for deal in deals
        if get_deal_key(deal) not in seen_keys
    ]


def collect_all_deals():
    """
    Collect deals from every enabled GamerQuest source.
    """

    collected = []

    # Steam
    try:
        steam_deals = fetch_steam_specials()

        for deal in steam_deals:
            if should_accept_deal(deal):
                collected.append(deal)

        print(
            f"Steam qualifying deals: "
            f"{sum(1 for d in steam_deals if should_accept_deal(d))}"
        )

    except Exception as exc:
        print(
            f"WARNING: Steam collector failed: {exc}"
        )

    # CheapShark
    try:
        cheapshark_deals = fetch_cheapshark_deals()

        for deal in cheapshark_deals:
            if should_accept_deal(deal):
                collected.append(deal)

        print(
            f"CheapShark qualifying deals: "
            f"{sum(1 for d in cheapshark_deals if should_accept_deal(d))}"
        )

    except Exception as exc:
        print(
            f"WARNING: CheapShark collector failed: {exc}"
        )

    # Epic
    try:
        epic_deals = fetch_epic_free_games()

        collected.extend(epic_deals)

        print(
            f"Epic qualifying deals: "
            f"{len(epic_deals)}"
        )

    except Exception as exc:
        print(
            f"WARNING: Epic collector failed: {exc}"
        )

    return deduplicate_deals(collected)

from deals.aggregator import (
    collect_all_deals,
    filter_new_deals,
    get_deal_key,
    load_seen_deals,
)


def main():
    print("=" * 70)
    print("GamerQuest Combined Deals Pipeline")
    print("=" * 70)

    deals = collect_all_deals()

    print()
    print(f"Total qualifying unique deals: {len(deals)}")

    seen_keys = load_seen_deals()

    print(
        f"Deals already known: "
        f"{len(seen_keys)}"
    )

    new_deals = filter_new_deals(
        deals,
        seen_keys,
    )

    print(
        f"NEW deals found: "
        f"{len(new_deals)}"
    )

    if not new_deals:
        print()
        print("No new GamerQuest deals.")
        return

    print()
    print("NEW DEALS")
    print("=" * 70)

    for deal in new_deals:
        print()
        print("-" * 70)
        print(
            f"GAME: "
            f"{deal.get('title')}"
        )
        print(
            f"STORE: "
            f"{deal.get('store')}"
        )
        print(
            f"ORIGINAL PRICE: "
            f"{deal.get('original_price')}"
        )
        print(
            f"CURRENT PRICE: "
            f"{deal.get('current_price')}"
        )
        print(
            f"DISCOUNT: "
            f"{deal.get('discount_percent')}%"
        )
        print(
            f"URL: "
            f"{deal.get('url')}"
        )
        print(
            f"DEAL ID: "
            f"{get_deal_key(deal)}"
        )

        if deal.get("expires_at"):
            print(
                f"EXPIRES: "
                f"{deal.get('expires_at')}"
            )

    print()
    print("=" * 70)


if __name__ == "__main__":
    main()

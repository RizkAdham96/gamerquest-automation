from deals.cheapshark import fetch_deals
from deals.filter import should_accept_deal


def main():
    print("=" * 70)
    print("GamerQuest Deal Scanner - CheapShark")
    print("=" * 70)

    deals = fetch_deals()

    print(f"\nDeals fetched: {len(deals)}")

    accepted = []

    for deal in deals:
        if should_accept_deal(deal):
            accepted.append(deal)

    print(f"FREE / 90%+ accepted: {len(accepted)}")

    if not accepted:
        print("\nNo qualifying deals found.")
        return

    print("\nQUALIFYING DEALS")

    for deal in accepted:
        print("\n" + "-" * 70)
        print(f"GAME: {deal['title']}")
        print(f"STORE ID: {deal['store']}")
        print(f"NORMAL PRICE: ${deal['original_price']:.2f}")
        print(f"SALE PRICE: ${deal['current_price']:.2f}")
        print(f"DISCOUNT: {deal['discount_percent']}%")

        if deal.get("steam_app_id"):
            print(f"STEAM APP ID: {deal['steam_app_id']}")

        print(f"DEAL: {deal['url']}")

    print("\n" + "=" * 70)
    print(f"TOTAL QUALIFYING DEALS: {len(accepted)}")
    print("=" * 70)


if __name__ == "__main__":
    main()

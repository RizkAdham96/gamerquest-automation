from deals.filter import should_accept_deal
from deals.steam import fetch_steam_specials


def main():
    print("=" * 60)
    print("GamerQuest Steam Deal Scanner")
    print("=" * 60)

    deals = fetch_steam_specials()

    print(f"\nSteam deals found: {len(deals)}")

    accepted = []

    for deal in deals:
        if should_accept_deal(deal):
            accepted.append(deal)

    print(f"Free / 90%+ deals accepted: {len(accepted)}")

    if not accepted:
        print("\nNo qualifying Steam deals currently found.")
        return

    print("\nQUALIFYING DEALS\n")

    for deal in accepted:
        print("-" * 60)
        print(f"GAME: {deal['title']}")
        print(f"STORE: {deal['store']}")
        print(f"ORIGINAL PRICE: €{deal['original_price']:.2f}")
        print(f"CURRENT PRICE: €{deal['current_price']:.2f}")
        print(f"DISCOUNT: {deal['discount_percent']}%")
        print(f"URL: {deal['url']}")

    print("-" * 60)


if __name__ == "__main__":
    main()

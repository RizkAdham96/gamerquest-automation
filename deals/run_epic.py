from deals.epic import fetch_epic_free_games


def main():
    print("=" * 70)
    print("GamerQuest Epic Free Games Scanner")
    print("=" * 70)

    games = fetch_epic_free_games()

    print(
        f"\nCurrent Epic free games found: "
        f"{len(games)}"
    )

    if not games:
        print(
            "\nNo active Epic free games "
            "were detected."
        )
        return

    for game in games:
        print("\n" + "-" * 70)

        print(
            f"GAME: {game['title']}"
        )

        print(
            f"STORE: {game['store']}"
        )

        print(
            f"NORMAL PRICE: "
            f"€{game['original_price']:.2f}"
        )

        print(
            "CURRENT PRICE: FREE"
        )

        print(
            f"DISCOUNT: "
            f"{game['discount_percent']}%"
        )

        print(
            f"START: "
            f"{game.get('starts_at')}"
        )

        print(
            f"END: "
            f"{game.get('expires_at')}"
        )

        print(
            f"URL: {game['url']}"
        )

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()

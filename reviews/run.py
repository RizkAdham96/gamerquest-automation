from reviews.discovery import discover_game_queries
from reviews.pipeline import build_review_record
from reviews.steam import fetch_app_details, fetch_review_summary, search_game
from reviews.wordpress import WordPressPublisher

MAX_GAMES_PER_RUN = 3


def run(max_games=MAX_GAMES_PER_RUN):
    queries = discover_game_queries(limit=max_games)
    if not queries:
        print("No game candidates found in GamerQuest feeds.")
        return

    publisher = WordPressPublisher()
    completed = 0
    failed = 0

    for query in queries:
        print(f"Review candidate: {query}")
        try:
            match = search_game(query)
            if not match:
                print(f"SKIP: no Steam match for {query}")
                continue
            appid = int(match["id"])
            details = fetch_app_details(appid)
            if not details:
                print(f"SKIP: Steam details unavailable for {query} ({appid})")
                continue
            summary = fetch_review_summary(appid)
            if not summary.get("total_reviews"):
                print(f"SKIP: no Steam reviews for {details.get('name', query)}")
                continue
            record = build_review_record(details, summary)
            publisher.publish(record)
            completed += 1
        except Exception as exc:
            failed += 1
            print(f"ERROR: {query}: {exc}")

    print(f"Tests & Avis run complete: completed={completed}, failed={failed}")
    if completed == 0 and failed:
        raise RuntimeError("All review candidates failed")


if __name__ == "__main__":
    run()

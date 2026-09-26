import json
from datetime import datetime, timezone
from pathlib import Path

from reviews.discovery import discover_game_queries
from reviews.pipeline import build_review_record
from reviews.steam import fetch_app_details, fetch_review_summary, search_game
from reviews.wordpress import WordPressPublisher

MAX_GAMES_PER_RUN = 15
STATUS_FILE = Path("reviews-run-status.json")


def _write_status(*, selected, published, existing, skipped, errors):
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "selected": selected,
        "published": published,
        "existing": existing,
        "skipped": skipped,
        "failed": len(errors),
        "errors": errors,
    }
    STATUS_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def run(max_games=MAX_GAMES_PER_RUN):
    queries = discover_game_queries(limit=max_games)
    if not queries:
        status = _write_status(
            selected=0,
            published=0,
            existing=0,
            skipped=0,
            errors=[],
        )
        print("No game candidates found in GamerQuest feeds or starter catalog.")
        print(f"Tests & Avis status: {status}")
        return status

    publisher = WordPressPublisher()
    published = 0
    existing = 0
    skipped = 0
    errors = []

    for query in queries:
        print(f"Review candidate: {query}")
        try:
            match = search_game(query)
            if not match:
                skipped += 1
                print(f"SKIP: no Steam match for {query}")
                continue
            appid = int(match["id"])
            details = fetch_app_details(appid)
            if not details:
                skipped += 1
                print(f"SKIP: Steam details unavailable for {query} ({appid})")
                continue
            summary = fetch_review_summary(appid)
            if not summary.get("total_reviews"):
                skipped += 1
                print(f"SKIP: no Steam reviews for {details.get('name', query)}")
                continue
            record = build_review_record(details, summary)
            result = publisher.publish(record)
            action = str(result.get("_gq_action", "")).strip().lower()
            if action == "published":
                published += 1
            elif action == "existing":
                existing += 1
            else:
                raise RuntimeError(
                    f"WordPress publisher returned unknown action for {query}: {action or 'missing'}"
                )
        except Exception as exc:
            message = f"{query}: {exc}"
            errors.append(message)
            print(f"ERROR: {message}")

    status = _write_status(
        selected=len(queries),
        published=published,
        existing=existing,
        skipped=skipped,
        errors=errors,
    )
    print(
        "Tests & Avis run complete: "
        f"selected={len(queries)}, published={published}, existing={existing}, "
        f"skipped={skipped}, failed={len(errors)}"
    )

    if errors:
        raise RuntimeError(
            f"Tests & Avis finished with {len(errors)} failed candidate(s); "
            "see reviews-run-status.json for details"
        )

    return status


if __name__ == "__main__":
    run()

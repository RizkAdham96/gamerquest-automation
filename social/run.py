import json
from pathlib import Path

from social.sources import get_all_content
from social.creative_brain import choose_best_idea
from social.carousel_writer import build_carousel
from social.config import MINIMUM_PUBLISH_SCORE


OUTPUT_FILE = Path("social-output.json")


def save_output(data):
    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def build_candidate_ideas(content):
    """
    Temporary placeholder.

    In the next step, this function will be replaced by
    the AI idea-generation layer using our separate
    social credentials.

    For now, we return no ideas.
    """
    return []


def run():
    content = get_all_content()

    print(f"Social content items found: {len(content)}")

    if not content:
        print("No GamerQuest content available.")
        save_output(
            {
                "status": "skipped",
                "reason": "no_content",
            }
        )
        return

    ideas = build_candidate_ideas(content)

    print(f"Candidate ideas generated: {len(ideas)}")

    if not ideas:
        print("No social ideas generated.")
        save_output(
            {
                "status": "skipped",
                "reason": "no_ideas",
            }
        )
        return

    best_idea = choose_best_idea(ideas)

    if not best_idea:
        print("All ideas were rejected.")
        save_output(
            {
                "status": "skipped",
                "reason": "repetitive_or_invalid",
            }
        )
        return

    score = best_idea.get("total_score", 0)

    print(f"Best social idea score: {score}")

    if score < MINIMUM_PUBLISH_SCORE:
        print("Best idea is below minimum quality score.")
        save_output(
            {
                "status": "skipped",
                "reason": "low_score",
                "best_score": score,
            }
        )
        return

    carousel = build_carousel(best_idea)

    if not carousel:
        print("Carousel structure is invalid.")
        save_output(
            {
                "status": "skipped",
                "reason": "invalid_carousel",
            }
        )
        return

    result = {
        "status": "ready",
        "carousel": carousel,
    }

    save_output(result)

    print("Social carousel successfully created.")
    print(f"Output saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    run()

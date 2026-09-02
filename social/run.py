import json
from pathlib import Path

from social.sources import get_all_content
from social.creative_brain import choose_best_idea
from social.carousel_writer import build_carousel
from social.config import MINIMUM_PUBLISH_SCORE
from social import idea_generator


OUTPUT_FILE = Path("social-output.json")


def save_output(data):
    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )


def build_candidate_ideas(content):
    """
    Generate social carousel ideas using the
    GamerQuest AI idea generator.
    """
    return idea_generator.generate_ideas(content)


def run():
    # ---------------------------------------------------------
    # 1. Load existing GamerQuest content
    # ---------------------------------------------------------

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

    # ---------------------------------------------------------
    # 2. Ask AI to generate candidate carousel ideas
    # ---------------------------------------------------------

    try:
        ideas = build_candidate_ideas(content)

    except Exception as error:
        print(f"AI idea generation failed: {error}")

        save_output(
            {
                "status": "error",
                "reason": "ai_generation_failed",
                "error": str(error),
            }
        )

        return

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

    # ---------------------------------------------------------
    # 3. Remove repetitive ideas and select the best one
    # ---------------------------------------------------------

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

    # ---------------------------------------------------------
    # 4. Check quality score
    # ---------------------------------------------------------

    score = best_idea.get("total_score", 0)

    print(f"Best social idea score: {score}")

    if score < MINIMUM_PUBLISH_SCORE:
        print(
            "Best idea is below minimum quality score."
        )

        save_output(
            {
                "status": "skipped",
                "reason": "low_score",
                "best_score": score,
            }
        )

        return

    # ---------------------------------------------------------
    # 5. Build final carousel package
    # ---------------------------------------------------------

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

    # ---------------------------------------------------------
    # 6. Save result
    #
    # IMPORTANT:
    # Nothing is published to Instagram/Facebook here.
    # ---------------------------------------------------------

    result = {
        "status": "ready",
        "carousel": carousel,
    }

    save_output(result)

    print("Social carousel successfully created.")
    print(f"Output saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    run()

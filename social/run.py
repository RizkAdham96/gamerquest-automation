import json
import time
from pathlib import Path

from social.sources import get_all_content
from social.idea_generator import (
    generate_ideas,
    expand_idea,
    verify_carousel,
    repair_carousel,
    find_source_item,
)
from social.scorer import score_idea
from social.carousel_writer import build_carousel
from social.history import (
    load_history,
    save_history,
)


OUTPUT_FILE = Path(
    "social-output.json"
)

MIN_SOCIAL_SCORE = 60

GROQ_WAIT_SECONDS = 25

MAX_REPAIR_ATTEMPTS = 2


# =========================================================
# OUTPUT
# =========================================================

def write_output(payload):
    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            payload,
            file,
            ensure_ascii=False,
            indent=2,
        )


# =========================================================
# PACING
# =========================================================

def wait_for_groq(label):
    print(
        f"Groq pacing: waiting "
        f"{GROQ_WAIT_SECONDS}s "
        f"before {label}..."
    )

    time.sleep(
        GROQ_WAIT_SECONDS
    )


# =========================================================
# FACT CHECK HELPERS
# =========================================================

def fact_check_passed(result):
    return (
        isinstance(result, dict)
        and result.get("valid") is True
    )


def unsupported_claims(result):
    if not isinstance(result, dict):
        return []

    value = result.get(
        "unsupported_claims",
        [],
    )

    if isinstance(value, list):
        return value

    return []


def fact_check_reason(result):
    if not isinstance(result, dict):
        return ""

    return str(
        result.get("reason", "")
    ).strip()


# =========================================================
# MAIN
# =========================================================

def run():

    # =====================================================
    # LOAD CONTENT
    # =====================================================

    content = get_all_content()

    print(
        f"Social content items found: "
        f"{len(content)}"
    )

    if not content:
        payload = {
            "status": "skipped",
            "reason": "no_content",
        }

        write_output(payload)
        return payload

    # =====================================================
    # HISTORY
    # =====================================================

    history = load_history()

    # =====================================================
    # GENERATE IDEAS
    # =====================================================

    ideas = generate_ideas(
        content
    )

    print(
        f"Candidate ideas generated: "
        f"{len(ideas)}"
    )

    if not ideas:
        payload = {
            "status": "skipped",
            "reason":
                "no_source_linked_ideas",
        }

        write_output(payload)
        return payload

    # =====================================================
    # SCORE IDEAS
    # =====================================================

    scored = []

    for idea in ideas:
        if not isinstance(
            idea,
            dict,
        ):
            continue

        source_id = idea.get(
            "source_id"
        )

        source_item = (
            find_source_item(
                content,
                source_id,
            )
        )

        if not source_item:
            print(
                "Rejected concept because "
                "source_id does not exist: "
                f"{source_id}"
            )

            continue

        score = score_idea(
            idea
        )

        scored_idea = (
            idea.copy()
        )

        scored_idea[
            "total_score"
        ] = score

        scored.append(
            scored_idea
        )

    if not scored:
        payload = {
            "status": "skipped",
            "reason":
                "no_valid_source_linked_ideas",
        }

        write_output(payload)
        return payload

    scored.sort(
        key=lambda item:
            item.get(
                "total_score",
                0,
            ),
        reverse=True,
    )

    best_idea = scored[0]

    best_score = (
        best_idea.get(
            "total_score",
            0,
        )
    )

    source_id = (
        best_idea.get(
            "source_id",
            ""
        )
    )

    source_item = (
        find_source_item(
            content,
            source_id,
        )
    )

    if not source_item:
        payload = {
            "status": "skipped",
            "reason":
                "selected_source_not_found",
            "source_id":
                source_id,
        }

        write_output(payload)
        return payload

    print(
        f"Best social idea score: "
        f"{best_score}"
    )

    print(
        "Selected source_id: "
        f"{source_id}"
    )

    print(
        "Selected exact article: "
        f"{source_item.get('title', '')}"
    )

    # =====================================================
    # SCORE THRESHOLD
    # =====================================================

    if best_score < MIN_SOCIAL_SCORE:
        payload = {
            "status": "skipped",
            "reason":
                "score_too_low",
            "score":
                best_score,
            "source_id":
                source_id,
            "idea":
                best_idea,
        }

        write_output(payload)
        return payload

    # =====================================================
    # IMPORTANT:
    # FROM HERE ON, ONLY ONE ARTICLE IS AVAILABLE
    # =====================================================

    exact_content = [
        source_item
    ]

    # =====================================================
    # GENERATE CAROUSEL
    # =====================================================

    wait_for_groq(
        "carousel generation"
    )

    carousel_package = (
        expand_idea(
            best_idea,
            exact_content,
        )
    )

    if not isinstance(
        carousel_package,
        dict,
    ):
        payload = {
            "status": "skipped",
            "reason":
                "carousel_generation_failed",
            "source_id":
                source_id,
        }

        write_output(payload)
        return payload

    slides = (
        carousel_package.get(
            "slides",
            [],
        )
    )

    if (
        not isinstance(
            slides,
            list,
        )
        or len(slides) != 3
    ):
        payload = {
            "status": "skipped",
            "reason":
                "invalid_slide_count",
            "source_id":
                source_id,
        }

        write_output(payload)
        return payload

    # =====================================================
    # FACT CHECK
    # =====================================================

    wait_for_groq(
        "first fact-check"
    )

    fact_check = (
        verify_carousel(
            carousel_package,
            exact_content,
        )
    )

    repair_attempts = 0

    # =====================================================
    # REPAIR LOOP
    # =====================================================

    while (
        not fact_check_passed(
            fact_check
        )
        and repair_attempts
        < MAX_REPAIR_ATTEMPTS
    ):

        repair_attempts += 1

        claims = unsupported_claims(
            fact_check
        )

        reason = fact_check_reason(
            fact_check
        )

        print("")
        print(
            "Fact-check failed."
        )

        print(
            f"Repair attempt: "
            f"{repair_attempts}/"
            f"{MAX_REPAIR_ATTEMPTS}"
        )

        for claim in claims:
            print(
                f"Unsupported: {claim}"
            )

        if reason:
            print(
                f"Reason: {reason}"
            )

        wait_for_groq(
            f"repair {repair_attempts}"
        )

        carousel_package = (
            repair_carousel(
                carousel_package,
                exact_content,
                claims,
            )
        )

        wait_for_groq(
            "fact-check after "
            f"repair {repair_attempts}"
        )

        fact_check = (
            verify_carousel(
                carousel_package,
                exact_content,
            )
        )

    # =====================================================
    # HARD STOP IF FACTS STILL FAIL
    # =====================================================

    if not fact_check_passed(
        fact_check
    ):
        payload = {
            "status": "skipped",
            "reason":
                "unsupported_claims_after_repair",
            "source_id":
                source_id,
            "source_title":
                source_item.get(
                    "title",
                    "",
                ),
            "unsupported_claims":
                unsupported_claims(
                    fact_check
                ),
            "fact_check_reason":
                fact_check_reason(
                    fact_check
                ),
            "repair_attempts":
                repair_attempts,
        }

        write_output(payload)

        print(
            "Carousel rejected after "
            "final fact-check."
        )

        return payload

    # =====================================================
    # BUILD CAROUSEL
    # =====================================================

    carousel = build_carousel(
        carousel_package
    )

    if not isinstance(
        carousel,
        dict,
    ):
        payload = {
            "status": "skipped",
            "reason":
                "carousel_build_failed",
        }

        write_output(payload)
        return payload

    carousel[
        "source_id"
    ] = source_id

    final_slides = (
        carousel.get(
            "slides",
            [],
        )
    )

    if len(final_slides) != 3:
        payload = {
            "status": "skipped",
            "reason":
                "final_invalid_slide_count",
        }

        write_output(payload)
        return payload

    # =====================================================
    # HISTORY
    # =====================================================

    history_entry = {
        "source_id":
            source_id,
        "topic":
            carousel.get(
                "topic",
                "",
            ),
        "angle":
            carousel.get(
                "angle",
                "",
            ),
        "format":
            carousel.get(
                "format",
                "",
            ),
        "hook":
            carousel.get(
                "hook",
                "",
            ),
        "cta":
            carousel.get(
                "cta",
                "",
            ),
        "score":
            best_score,
    }

    history.append(
        history_entry
    )

    save_history(
        history
    )

    # =====================================================
    # FINAL OUTPUT
    # =====================================================

    payload = {
        "status":
            "ready",

        "fact_checked":
            True,

        "source_id":
            source_id,

        "source_title":
            source_item.get(
                "title",
                "",
            ),

        "score":
            best_score,

        "idea":
            best_idea,

        "carousel":
            carousel,

        "caption":
            carousel.get(
                "caption",
                "",
            ),

        "hashtags":
            carousel.get(
                "hashtags",
                [],
            ),

        "cta":
            carousel.get(
                "cta",
                "",
            ),

        "repair_attempts":
            repair_attempts,
    }

    write_output(
        payload
    )

    print("")
    print(
        "======================================"
    )

    print(
        "SOCIAL GENERATION SUCCESS"
    )

    print(
        "======================================"
    )

    print(
        f"Source ID: {source_id}"
    )

    print(
        "Exact article: "
        f"{source_item.get('title', '')}"
    )

    print(
        f"Score: {best_score}"
    )

    print(
        f"Slides: {len(final_slides)}"
    )

    print(
        "Fact checked against "
        "ONE exact article: YES"
    )

    print(
        "======================================"
    )

    return payload


if __name__ == "__main__":
    run()

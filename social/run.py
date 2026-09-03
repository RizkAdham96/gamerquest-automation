import json
import time
from pathlib import Path

from social.sources import get_all_content
from social.idea_generator import (
    generate_ideas,
    expand_idea,
    verify_carousel,
    repair_carousel,
)
from social.scorer import score_idea
from social.carousel_writer import build_carousel
from social.history import (
    load_history,
    save_history,
)


# =========================================================
# CONFIG
# =========================================================

OUTPUT_FILE = Path("social-output.json")

MIN_SOCIAL_SCORE = 60

# Pause between Groq calls to reduce free-plan rate-limit issues
GROQ_WAIT_SECONDS = 25

# Original repair + one extra repair attempt
MAX_REPAIR_ATTEMPTS = 2


# =========================================================
# HELPERS
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


def wait_for_groq(label):
    print(
        f"Groq pacing: waiting "
        f"{GROQ_WAIT_SECONDS}s "
        f"before {label}..."
    )

    time.sleep(GROQ_WAIT_SECONDS)


def get_unsupported_claims(fact_check):
    if not isinstance(fact_check, dict):
        return []

    claims = fact_check.get(
        "unsupported_claims",
        [],
    )

    if not isinstance(claims, list):
        return []

    return claims


def get_fact_check_reason(fact_check):
    if not isinstance(fact_check, dict):
        return ""

    return str(
        fact_check.get("reason", "")
    ).strip()


def fact_check_passed(fact_check):
    if not isinstance(fact_check, dict):
        return False

    return fact_check.get("valid") is True


# =========================================================
# MAIN
# =========================================================

def run():

    # =====================================================
    # 1. LOAD GAMERQUEST CONTENT
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
    # 2. LOAD HISTORY
    # =====================================================

    history = load_history()

    # =====================================================
    # 3. GENERATE 3 SOCIAL CONCEPTS
    #
    # IMPORTANT:
    # generate_ideas() accepts ONLY content.
    # History is already handled inside idea_generator.py.
    # =====================================================

    ideas = generate_ideas(content)

    print(
        f"Candidate ideas generated: "
        f"{len(ideas)}"
    )

    if not ideas:
        payload = {
            "status": "skipped",
            "reason": "no_ideas",
        }

        write_output(payload)

        return payload

    # =====================================================
    # 4. SCORE IDEAS
    #
    # score_idea() accepts ONLY one idea.
    # =====================================================

    scored_ideas = []

    for idea in ideas:

        if not isinstance(idea, dict):
            continue

        score = score_idea(idea)

        scored_idea = idea.copy()

        scored_idea[
            "total_score"
        ] = score

        scored_ideas.append(
            scored_idea
        )

    if not scored_ideas:
        payload = {
            "status": "skipped",
            "reason": "no_valid_ideas",
        }

        write_output(payload)

        return payload

    scored_ideas.sort(
        key=lambda item: item.get(
            "total_score",
            0,
        ),
        reverse=True,
    )

    best_idea = scored_ideas[0]

    best_score = best_idea.get(
        "total_score",
        0,
    )

    print(
        f"Best social idea score: "
        f"{best_score}"
    )

    print(
        f"Selected topic: "
        f"{best_idea.get('topic', '')}"
    )

    # =====================================================
    # 5. MINIMUM SCORE CHECK
    # =====================================================

    if best_score < MIN_SOCIAL_SCORE:

        payload = {
            "status": "skipped",
            "reason": "score_too_low",
            "score": best_score,
            "idea": best_idea,
        }

        write_output(payload)

        return payload

    # =====================================================
    # 6. WAIT BEFORE CAROUSEL GENERATION
    # =====================================================

    wait_for_groq(
        "carousel generation"
    )

    # =====================================================
    # 7. EXPAND WINNING IDEA
    #
    # expand_idea(idea, content)
    # =====================================================

    carousel_package = expand_idea(
        best_idea,
        content,
    )

    if not isinstance(
        carousel_package,
        dict,
    ):
        payload = {
            "status": "skipped",
            "reason":
                "carousel_generation_failed",
        }

        write_output(payload)

        return payload

    slides = carousel_package.get(
        "slides",
        [],
    )

    if (
        not isinstance(slides, list)
        or len(slides) != 3
    ):
        payload = {
            "status": "skipped",
            "reason":
                "invalid_slide_count",
            "slide_count":
                len(slides)
                if isinstance(
                    slides,
                    list,
                )
                else 0,
        }

        write_output(payload)

        return payload

    print(
        "Carousel draft generated: "
        "3 slides."
    )

    # =====================================================
    # 8. WAIT BEFORE FIRST FACT CHECK
    # =====================================================

    wait_for_groq(
        "first fact-check"
    )

    # =====================================================
    # 9. FIRST FACT CHECK
    #
    # verify_carousel(idea, content)
    # =====================================================

    fact_check = verify_carousel(
        carousel_package,
        content,
    )

    repair_attempts = 0

    # =====================================================
    # 10. REPAIR LOOP
    #
    # Fact check
    #    ↓
    # Repair #1
    #    ↓
    # Fact check
    #    ↓
    # Repair #2
    #    ↓
    # Final fact check
    # =====================================================

    while (
        not fact_check_passed(
            fact_check
        )
        and repair_attempts
        < MAX_REPAIR_ATTEMPTS
    ):

        repair_attempts += 1

        unsupported_claims = (
            get_unsupported_claims(
                fact_check
            )
        )

        reason = (
            get_fact_check_reason(
                fact_check
            )
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

        if unsupported_claims:

            print(
                "Unsupported claims:"
            )

            for claim in (
                unsupported_claims
            ):
                print(
                    f"- {claim}"
                )

        if reason:

            print(
                "Fact-check reason:"
            )

            print(reason)

        # =============================================
        # WAIT BEFORE REPAIR
        # =============================================

        wait_for_groq(
            f"repair "
            f"{repair_attempts}"
        )

        # =============================================
        # REPAIR
        #
        # IMPORTANT:
        #
        # Your real function signature is:
        #
        # repair_carousel(
        #     idea,
        #     content,
        #     unsupported_claims,
        # )
        #
        # =============================================

        carousel_package = (
            repair_carousel(
                carousel_package,
                content,
                unsupported_claims,
            )
        )

        if not isinstance(
            carousel_package,
            dict,
        ):
            payload = {
                "status": "skipped",
                "reason":
                    "repair_failed",
                "repair_attempts":
                    repair_attempts,
            }

            write_output(payload)

            return payload

        repaired_slides = (
            carousel_package.get(
                "slides",
                [],
            )
        )

        if (
            not isinstance(
                repaired_slides,
                list,
            )
            or len(
                repaired_slides
            ) != 3
        ):

            payload = {
                "status": "skipped",
                "reason":
                    "repair_changed_slide_count",
                "repair_attempts":
                    repair_attempts,
                "slide_count":
                    len(
                        repaired_slides
                    )
                    if isinstance(
                        repaired_slides,
                        list,
                    )
                    else 0,
            }

            write_output(payload)

            return payload

        # =============================================
        # WAIT BEFORE CHECKING REPAIR
        # =============================================

        wait_for_groq(
            f"fact-check after "
            f"repair "
            f"{repair_attempts}"
        )

        # =============================================
        # CHECK REPAIRED CAROUSEL
        # =============================================

        fact_check = (
            verify_carousel(
                carousel_package,
                content,
            )
        )

        if fact_check_passed(
            fact_check
        ):

            print(
                f"Repair "
                f"{repair_attempts} "
                f"passed fact-check."
            )

    # =====================================================
    # 11. GIVE UP ONLY AFTER BOTH REPAIR ATTEMPTS
    # =====================================================

    if not fact_check_passed(
        fact_check
    ):

        unsupported_claims = (
            get_unsupported_claims(
                fact_check
            )
        )

        reason = (
            get_fact_check_reason(
                fact_check
            )
        )

        payload = {
            "status": "skipped",
            "reason":
                "unsupported_claims_after_repair",
            "unsupported_claims":
                unsupported_claims,
            "fact_check_reason":
                reason,
            "repair_attempts":
                repair_attempts,
        }

        write_output(payload)

        print("")
        print(
            "Social carousel skipped."
        )

        print(
            "Unsupported claims "
            "remained after "
            f"{repair_attempts} "
            "repair attempts."
        )

        return payload

    # =====================================================
    # 12. FACT CHECK PASSED
    # =====================================================

    print("")
    print(
        "Carousel passed "
        "fact-check."
    )

    # =====================================================
    # 13. BUILD FINAL CAROUSEL
    #
    # build_carousel(idea)
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

    final_slides = carousel.get(
        "slides",
        [],
    )

    if (
        not isinstance(
            final_slides,
            list,
        )
        or len(
            final_slides
        ) != 3
    ):

        payload = {
            "status": "skipped",
            "reason":
                "final_carousel_invalid_slide_count",
            "slide_count":
                len(final_slides)
                if isinstance(
                    final_slides,
                    list,
                )
                else 0,
        }

        write_output(payload)

        return payload

    # =====================================================
    # 14. SAVE HISTORY
    # =====================================================

    history_entry = {
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
    # 15. FINAL SOCIAL OUTPUT
    #
    # render.py reads this file afterwards.
    # =====================================================

    payload = {
        "status": "ready",
        "fact_checked": True,
        "score": best_score,
        "idea": best_idea,
        "carousel": carousel,
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

    write_output(payload)

    # =====================================================
    # SUCCESS LOG
    # =====================================================

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
        f"Topic: "
        f"{carousel.get('topic', '')}"
    )

    print(
        f"Score: "
        f"{best_score}"
    )

    print(
        f"Slides: "
        f"{len(final_slides)}"
    )

    print(
        f"Repair attempts used: "
        f"{repair_attempts}"
    )

    print(
        "Fact checked: YES"
    )

    print(
        f"Output: "
        f"{OUTPUT_FILE}"
    )

    print(
        "======================================"
    )

    return payload


# =========================================================
# CLI
# =========================================================

if __name__ == "__main__":
    run()

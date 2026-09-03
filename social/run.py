import inspect
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

# Groq Free Plan pacing
GROQ_WAIT_SECONDS = 25

# First repair + one extra repair attempt
MAX_REPAIR_ATTEMPTS = 2


# =========================================================
# OUTPUT
# =========================================================

def _write_output(payload):
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
# GROQ PACING
# =========================================================

def _sleep_before(label):
    print(
        f"Groq pacing: waiting "
        f"{GROQ_WAIT_SECONDS}s "
        f"before {label}..."
    )

    time.sleep(
        GROQ_WAIT_SECONDS
    )


# =========================================================
# FACT-CHECK HELPERS
# =========================================================

def _fact_check_passed(result):
    """
    Support the different valid/pass field names that may
    exist in idea_generator.py.
    """

    if not isinstance(result, dict):
        return False

    if result.get("valid") is True:
        return True

    if result.get("passed") is True:
        return True

    if result.get("supported") is True:
        return True

    return False


def _unsupported_claims(result):
    if not isinstance(result, dict):
        return []

    claims = result.get(
        "unsupported_claims",
        [],
    )

    if isinstance(claims, list):
        return claims

    return []


def _fact_check_reason(result):
    if not isinstance(result, dict):
        return ""

    return str(
        result.get("reason")
        or result.get("fact_check_reason")
        or ""
    ).strip()


# =========================================================
# REPAIR COMPATIBILITY
# =========================================================

def _repair_package(
    carousel_package,
    fact_check,
    content,
):
    """
    Call the existing repair_carousel() while adapting to
    the parameter names already used in idea_generator.py.

    This avoids breaking the current implementation if its
    argument names/order are slightly different.
    """

    signature = inspect.signature(
        repair_carousel
    )

    parameter_names = list(
        signature.parameters.keys()
    )

    kwargs = {}

    for name in parameter_names:
        lowered = name.lower()

        # ---------------------------------------------
        # CAROUSEL / PACKAGE
        # ---------------------------------------------

        if any(
            token in lowered
            for token in (
                "carousel",
                "package",
                "draft",
            )
        ):
            kwargs[name] = carousel_package
            continue

        # ---------------------------------------------
        # FACT CHECK / VERIFICATION
        # ---------------------------------------------

        if any(
            token in lowered
            for token in (
                "fact",
                "verify",
                "verification",
                "check",
                "unsupported",
            )
        ):
            kwargs[name] = fact_check
            continue

        # ---------------------------------------------
        # SOURCE CONTENT
        # ---------------------------------------------

        if any(
            token in lowered
            for token in (
                "content",
                "source",
                "articles",
                "items",
            )
        ):
            kwargs[name] = content
            continue

    # If we successfully identified every required
    # argument, call using keywords.
    required_parameters = [
        name
        for name, parameter
        in signature.parameters.items()
        if (
            parameter.default
            is inspect.Parameter.empty
            and parameter.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        )
    ]

    if all(
        name in kwargs
        for name in required_parameters
    ):
        return repair_carousel(
            **kwargs
        )

    # -------------------------------------------------
    # FALLBACK
    #
    # Current GamerQuest implementation is expected to
    # use package + fact check + source content.
    # -------------------------------------------------

    try:
        return repair_carousel(
            carousel_package,
            fact_check,
            content,
        )

    except TypeError:
        pass

    # Alternative common order.
    try:
        return repair_carousel(
            carousel_package,
            content,
            fact_check,
        )

    except TypeError:
        pass

    # Some versions may only need package + content.
    return repair_carousel(
        carousel_package,
        content,
    )


# =========================================================
# MAIN SOCIAL PIPELINE
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

        _write_output(
            payload
        )

        return payload

    # =====================================================
    # 2. LOAD SOCIAL HISTORY
    # =====================================================

    history = load_history()

    # =====================================================
    # 3. GENERATE 3 SOCIAL IDEAS
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
            "reason": "no_ideas",
        }

        _write_output(
            payload
        )

        return payload

    # =====================================================
    # 4. SCORE IDEAS
    # =====================================================

    scored = []

    for idea in ideas:
        score = score_idea(
            idea,
            content=content,
            history=history,
        )

        scored.append(
            (
                score,
                idea,
            )
        )

    scored.sort(
        key=lambda pair: pair[0],
        reverse=True,
    )

    best_score, best_idea = (
        scored[0]
    )

    print(
        f"Best social idea score: "
        f"{best_score}"
    )

    # =====================================================
    # 5. MINIMUM QUALITY SCORE
    # =====================================================

    if best_score < MIN_SOCIAL_SCORE:
        payload = {
            "status": "skipped",
            "reason": "score_too_low",
            "score": best_score,
            "idea": best_idea,
        }

        _write_output(
            payload
        )

        return payload

    # =====================================================
    # 6. CREATE EXACTLY 3 SLIDES
    # =====================================================

    carousel_package = (
        expand_idea(
            best_idea,
            content,
        )
    )

    slides = carousel_package.get(
        "slides",
        [],
    )

    if len(slides) != 3:
        payload = {
            "status": "skipped",
            "reason": "invalid_slide_count",
            "slide_count": len(slides),
        }

        _write_output(
            payload
        )

        return payload

    # =====================================================
    # 7. FIRST FACT CHECK
    # =====================================================

    _sleep_before(
        "fact-check"
    )

    fact_check = verify_carousel(
        carousel_package,
        content,
    )

    # =====================================================
    # 8. REPAIR LOOP
    #
    # Before:
    #
    # fact check
    # → repair once
    # → still wrong
    # → abandon entire post
    #
    # Now:
    #
    # fact check
    # → repair 1
    # → check
    # → repair 2
    # → check
    # =====================================================

    repair_attempt = 0

    while (
        not _fact_check_passed(
            fact_check
        )
        and repair_attempt
        < MAX_REPAIR_ATTEMPTS
    ):

        repair_attempt += 1

        unsupported = (
            _unsupported_claims(
                fact_check
            )
        )

        reason = (
            _fact_check_reason(
                fact_check
            )
        )

        print(
            ""
        )

        print(
            "Fact-check failed."
        )

        print(
            f"Repair attempt: "
            f"{repair_attempt}/"
            f"{MAX_REPAIR_ATTEMPTS}"
        )

        if unsupported:
            print(
                "Unsupported claims:"
            )

            for claim in unsupported:
                print(
                    f"- {claim}"
                )

        if reason:
            print(
                "Fact-check reason:"
            )

            print(
                reason
            )

        # -------------------------------------------------
        # WAIT BEFORE GROQ REPAIR
        # -------------------------------------------------

        _sleep_before(
            f"repair {repair_attempt}"
        )

        # -------------------------------------------------
        # TARGETED REPAIR
        # -------------------------------------------------

        carousel_package = (
            _repair_package(
                carousel_package,
                fact_check,
                content,
            )
        )

        repaired_slides = (
            carousel_package.get(
                "slides",
                [],
            )
        )

        # Never allow repair to change 3-slide format.
        if len(repaired_slides) != 3:
            payload = {
                "status": "skipped",
                "reason":
                    "repair_changed_slide_count",
                "repair_attempt":
                    repair_attempt,
                "slide_count":
                    len(repaired_slides),
            }

            _write_output(
                payload
            )

            return payload

        # -------------------------------------------------
        # WAIT BEFORE RECHECK
        # -------------------------------------------------

        _sleep_before(
            f"fact-check after repair "
            f"{repair_attempt}"
        )

        # -------------------------------------------------
        # FACT CHECK REPAIRED VERSION
        # -------------------------------------------------

        fact_check = verify_carousel(
            carousel_package,
            content,
        )

        if _fact_check_passed(
            fact_check
        ):
            print(
                f"Carousel repair "
                f"{repair_attempt} "
                f"passed fact-check."
            )

    # =====================================================
    # 9. STILL UNSUPPORTED AFTER 2 REPAIRS
    # =====================================================

    if not _fact_check_passed(
        fact_check
    ):

        payload = {
            "status": "skipped",

            "reason":
                "unsupported_claims_after_repair",

            "unsupported_claims":
                _unsupported_claims(
                    fact_check
                ),

            "fact_check_reason":
                _fact_check_reason(
                    fact_check
                ),

            "repair_attempts":
                repair_attempt,
        }

        _write_output(
            payload
        )

        print(
            ""
        )

        print(
            "Social carousel skipped."
        )

        print(
            "Unsupported claims remained "
            "after both repair attempts."
        )

        return payload

    # =====================================================
    # 10. BUILD FINAL CAROUSEL
    # =====================================================

    carousel = build_carousel(
        carousel_package
    )

    final_slides = carousel.get(
        "slides",
        [],
    )

    if len(final_slides) != 3:
        payload = {
            "status": "skipped",
            "reason":
                "final_carousel_invalid_slide_count",
            "slide_count":
                len(final_slides),
        }

        _write_output(
            payload
        )

        return payload

    # =====================================================
    # 11. SAVE SOCIAL HISTORY
    # =====================================================

    history_entry = {
        "topic": carousel.get(
            "topic",
            best_idea.get(
                "topic",
                "",
            ),
        ),

        "hook": carousel.get(
            "hook",
            best_idea.get(
                "hook",
                "",
            ),
        ),

        "angle": carousel.get(
            "angle",
            best_idea.get(
                "angle",
                "",
            ),
        ),

        "score": best_score,
    }

    history.append(
        history_entry
    )

    save_history(
        history
    )

    # =====================================================
    # 12. READY FOR RENDERER
    # =====================================================

    payload = {
        "status": "ready",

        "fact_checked": True,

        "score": best_score,

        "idea": best_idea,

        "carousel": carousel,

        "caption": carousel.get(
            "caption",
            "",
        ),

        "hashtags": carousel.get(
            "hashtags",
            [],
        ),

        "cta": carousel.get(
            "cta",
            "",
        ),

        "repair_attempts":
            repair_attempt,
    }

    _write_output(
        payload
    )

    print(
        ""
    )

    print(
        "Social carousel successfully created."
    )

    print(
        f"Repair attempts used: "
        f"{repair_attempt}"
    )

    print(
        f"Output saved to: "
        f"{OUTPUT_FILE}"
    )

    return payload


# =========================================================
# CLI
# =========================================================

if __name__ == "__main__":
    run()

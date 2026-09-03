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


OUTPUT_FILE = Path("social-output.json")

MIN_SOCIAL_SCORE = 60

# Groq pacing
GROQ_WAIT_SECONDS = 25

# Allow up to 2 repair attempts total
MAX_REPAIR_ATTEMPTS = 2


# =========================================================
# HELPERS
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


def _sleep_before(label):
    print(
        f"Groq pacing: waiting "
        f"{GROQ_WAIT_SECONDS}s "
        f"before {label}..."
    )

    time.sleep(
        GROQ_WAIT_SECONDS
    )


def _fact_check_passed(result):
    if not isinstance(result, dict):
        return False

    return bool(
        result.get("valid")
        or result.get("passed")
        or result.get("supported")
    )


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

        _write_output(
            payload
        )

        return payload

    # =====================================================
    # LOAD HISTORY
    # =====================================================

    history = load_history()

    # =====================================================
    # GENERATE CONCEPTS
    # =====================================================

    ideas = generate_ideas(
        content,
        history=history,
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
    # SCORE IDEAS
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

    best_score, best_idea = scored[0]

    print(
        f"Best social idea score: "
        f"{best_score}"
    )

    # =====================================================
    # SCORE THRESHOLD
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
    # EXPAND INTO 3-SLIDE CAROUSEL
    # =====================================================

    carousel_package = expand_idea(
        best_idea,
        content,
    )

    # =====================================================
    # FIRST FACT-CHECK
    # =====================================================

    _sleep_before(
        "fact-check"
    )

    fact_check = verify_carousel(
        carousel_package,
        content,
    )

    # =====================================================
    # REPAIR LOOP
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

        unsupported = _unsupported_claims(
            fact_check
        )

        reason = _fact_check_reason(
            fact_check
        )

        print(
            f"Fact-check failed. "
            f"Repair attempt "
            f"{repair_attempt}/"
            f"{MAX_REPAIR_ATTEMPTS}."
        )

        if unsupported:
            print(
                "Unsupported claims: "
                + " | ".join(
                    str(claim)
                    for claim in unsupported
                )
            )

        if reason:
            print(
                "Fact-check reason: "
                + reason
            )

        _sleep_before(
            f"repair {repair_attempt}"
        )

        # Give repair_carousel the current package
        # and the exact failed fact-check so Groq can
        # correct only the unsupported statements.
        carousel_package = repair_carousel(
            carousel_package,
            fact_check,
            content,
        )

        _sleep_before(
            f"fact-check after repair "
            f"{repair_attempt}"
        )

        fact_check = verify_carousel(
            carousel_package,
            content,
        )

    # =====================================================
    # STILL FAILED AFTER 2 REPAIRS
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
            "Social carousel skipped: "
            "unsupported claims remained "
            "after repair attempts."
        )

        return payload

    # =====================================================
    # BUILD FINAL CAROUSEL
    # =====================================================

    carousel = build_carousel(
        carousel_package
    )

    # =====================================================
    # SAVE HISTORY
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
    # READY OUTPUT
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
        "repair_attempts": repair_attempt,
    }

    _write_output(
        payload
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

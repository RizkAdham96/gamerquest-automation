# =========================================================
# GAMERQUEST TRENDING SEO — END-TO-END PIPELINE V1
# SAFE MANUAL MODE: WORDPRESS DRAFT ONLY
# =========================================================

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

import scorer
import researcher

from writer import (
    build_writer_input,
    build_generation_request,
    generate_draft_with_ai,
    build_final_validation_request,
    run_final_validator,
    finalize_validated_draft,
)


# =========================================================
# PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

RESEARCH_FILE = (
    BASE_DIR
    / "research_results.json"
)

PIPELINE_RESULT_FILE = (
    BASE_DIR
    / "pipeline_result.json"
)


# =========================================================
# CONFIG
# =========================================================

# Critical safety setting.
# This first end-to-end version NEVER publishes publicly.
WORDPRESS_STATUS = "draft"

# Only one article per manual test run.
MAX_ARTICLES_PER_RUN = 1


# =========================================================
# BASIC HELPERS
# =========================================================

def load_json(path):
    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def save_json(path, data):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )

        file.write("\n")


def safe_string(value):
    return str(
        value or ""
    ).strip()


def utc_now():
    return (
        datetime.now(
            timezone.utc
        )
        .isoformat()
    )


def stop_result(
    status,
    reason,
    topic=None,
):
    result = {
        "status": status,
        "reason": reason,
        "topic": topic,
        "wordpress_status": None,
        "wordpress_post_id": None,
        "wordpress_url": None,
        "published": False,
        "created_at": utc_now(),
    }

    save_json(
        PIPELINE_RESULT_FILE,
        result,
    )

    print("")
    print("=" * 60)
    print("PIPELINE STOPPED SAFELY")
    print("=" * 60)
    print("STATUS:", status)
    print("REASON:", reason)
    print("=" * 60)

    return result


# =========================================================
# WORDPRESS CONFIG
# =========================================================

def get_wordpress_config():
    wp_url = safe_string(
        os.environ.get(
            "WP_URL",
            "",
        )
    ).rstrip("/")

    username = safe_string(
        os.environ.get(
            "WP_USERNAME",
            "",
        )
    )

    password = safe_string(
        os.environ.get(
            "WP_APP_PASSWORD",
            "",
        )
    )

    if (
        not wp_url
        or not username
        or not password
    ):
        return {}

    if not (
        wp_url.startswith(
            "https://"
        )
        or wp_url.startswith(
            "http://"
        )
    ):
        return {}

    return {
        "base_url": wp_url,
        "username": username,
        "application_password": (
            password
        ),
    }


# =========================================================
# RESEARCH SELECTION
# =========================================================

def get_safe_research_candidates(
    research_data,
):
    if not isinstance(
        research_data,
        dict,
    ):
        return []

    safe = []

    for topic in research_data.get(
        "topics",
        [],
    ):
        if not isinstance(
            topic,
            dict,
        ):
            continue

        fact_pack = topic.get(
            "fact_pack",
            {},
        )

        if not isinstance(
            fact_pack,
            dict,
        ):
            continue

        confirmed_facts = (
            fact_pack.get(
                "confirmed_facts",
                [],
            )
        )

        if not isinstance(
            confirmed_facts,
            list,
        ):
            continue

        # Writer must never run with zero
        # confirmed facts.
        if not confirmed_facts:
            continue

        if (
            safe_string(
                topic.get(
                    "research_status",
                    "",
                )
            )
            != "VERIFIED_FACTS_READY"
        ):
            continue

        safe.append(
            topic
        )

    return safe[
        :MAX_ARTICLES_PER_RUN
    ]


# =========================================================
# DRAFT-ONLY WORDPRESS BRIDGE
# =========================================================

def create_wordpress_draft(
    validated_draft,
    wp_config,
):
    """
    Real WordPress call, but hard-locked to status=draft.

    This function intentionally does NOT accept
    a status argument.

    That prevents an accidental caller from changing
    this manual test into public publishing.
    """

    if not isinstance(
        validated_draft,
        dict,
    ):
        return {
            "status": (
                "BLOCKED_INVALID_DRAFT"
            ),
            "published": False,
        }

    if (
        safe_string(
            validated_draft.get(
                "status",
                "",
            )
        )
        != "VALIDATED_DRAFT"
    ):
        return {
            "status": (
                "BLOCKED_NOT_VALIDATED_DRAFT"
            ),
            "published": False,
        }

    if (
        validated_draft.get(
            "publishable"
        )
        is not True
    ):
        return {
            "status": (
                "BLOCKED_NOT_PUBLISHABLE"
            ),
            "published": False,
        }

    if not isinstance(
        wp_config,
        dict,
    ):
        return {
            "status": (
                "BLOCKED_WORDPRESS_CONFIG"
            ),
            "published": False,
        }

    base_url = safe_string(
        wp_config.get(
            "base_url",
            "",
        )
    ).rstrip("/")

    username = safe_string(
        wp_config.get(
            "username",
            "",
        )
    )

    password = safe_string(
        wp_config.get(
            "application_password",
            "",
        )
    )

    if (
        not base_url
        or not username
        or not password
    ):
        return {
            "status": (
                "BLOCKED_WORDPRESS_CONFIG"
            ),
            "published": False,
        }

    title = safe_string(
        validated_draft.get(
            "title",
            "",
        )
    )

    content = safe_string(
        validated_draft.get(
            "content",
            "",
        )
    )

    meta_description = safe_string(
        validated_draft.get(
            "meta_description",
            "",
        )
    )

    if not title or not content:
        return {
            "status": (
                "BLOCKED_EMPTY_DRAFT"
            ),
            "published": False,
        }

    endpoint = (
        base_url
        + "/wp-json/wp/v2/posts"
    )

    # =====================================================
    # CRITICAL:
    # hard-coded DRAFT.
    # No parameter can override this.
    # =====================================================

    payload = {
        "title": title,
        "content": content,
        "status": "draft",
    }

    if meta_description:
        payload["excerpt"] = (
            meta_description
        )

    try:
        response = requests.post(
            endpoint,
            json=payload,
            auth=(
                username,
                password,
            ),
            timeout=30,
            headers={
                "Accept": (
                    "application/json"
                ),
                "User-Agent": (
                    "GamerQuest-Trending-SEO-"
                    "Pipeline-Draft/1.0"
                ),
            },
        )

    except Exception as error:
        return {
            "status": (
                "BLOCKED_WORDPRESS_UNAVAILABLE"
            ),
            "published": False,
            "error": (
                f"{type(error).__name__}: "
                f"{error}"
            ),
        }

    if (
        response.status_code < 200
        or response.status_code >= 300
    ):
        return {
            "status": (
                "BLOCKED_WORDPRESS_ERROR"
            ),
            "published": False,
            "http_status": (
                response.status_code
            ),
        }

    try:
        data = response.json()

    except Exception:
        return {
            "status": (
                "BLOCKED_INVALID_WORDPRESS_RESPONSE"
            ),
            "published": False,
        }

    if not isinstance(
        data,
        dict,
    ):
        return {
            "status": (
                "BLOCKED_INVALID_WORDPRESS_RESPONSE"
            ),
            "published": False,
        }

    post_id = data.get(
        "id"
    )

    wordpress_status = (
        safe_string(
            data.get(
                "status",
                "",
            )
        )
        .lower()
    )

    # =====================================================
    # FINAL DRAFT SAFETY ASSERTION
    # =====================================================

    if not post_id:
        return {
            "status": (
                "BLOCKED_INVALID_WORDPRESS_RESPONSE"
            ),
            "published": False,
        }

    if wordpress_status != "draft":
        return {
            "status": (
                "BLOCKED_WORDPRESS_STATUS_MISMATCH"
            ),
            "published": False,
            "wordpress_post_id": (
                post_id
            ),
            "wordpress_status": (
                wordpress_status
            ),
        }

    return {
        "status": (
            "WORDPRESS_DRAFT_CREATED"
        ),
        "published": False,
        "wordpress_status": "draft",
        "wordpress_post_id": post_id,
        "wordpress_url": safe_string(
            data.get(
                "link",
                "",
            )
        ),
    }


# =========================================================
# ONE TOPIC
# =========================================================

def process_research_topic(
    research_record,
    wp_config,
):
    topic_name = safe_string(
        research_record.get(
            "topic",
            "",
        )
    )

    print("")
    print("=" * 60)
    print("PROCESSING TRENDING SEO TOPIC")
    print("=" * 60)
    print(topic_name)

    # =====================================================
    # WRITER V1
    # =====================================================

    writer_input = (
        build_writer_input(
            research_record
        )
    )

    if (
        writer_input.get(
            "status"
        )
        != "READY_FOR_WRITING"
    ):
        return stop_result(
            status=(
                "SKIPPED_WRITER_GATE"
            ),
            reason=(
                "Writer did not receive "
                "source-backed confirmed facts."
            ),
            topic=topic_name,
        )

    confirmed_facts = (
        writer_input.get(
            "confirmed_facts",
            [],
        )
    )

    print(
        "Confirmed facts:",
        len(
            confirmed_facts
        ),
    )

    # =====================================================
    # WRITER V2
    # =====================================================

    generation_request = (
        build_generation_request(
            writer_input
        )
    )

    if (
        generation_request.get(
            "status"
        )
        != "READY_FOR_AI"
    ):
        return stop_result(
            status=(
                "SKIPPED_GENERATION_GATE"
            ),
            reason=(
                "Article generation request "
                "was not approved."
            ),
            topic=topic_name,
        )

    # =====================================================
    # WRITER V3
    # =====================================================

    print(
        "Generating article with Groq..."
    )

    generated_draft = (
        generate_draft_with_ai(
            generation_request
        )
    )

    if (
        generated_draft.get(
            "status"
        )
        != "DRAFT_PENDING_VALIDATION"
    ):
        return stop_result(
            status=(
                generated_draft.get(
                    "status",
                    "BLOCKED_GENERATION",
                )
            ),
            reason=(
                "Groq did not return a "
                "valid safe draft."
            ),
            topic=topic_name,
        )

    print(
        "Article generated."
    )

    print(
        "Publishable before validation:",
        generated_draft.get(
            "publishable",
        ),
    )

    # =====================================================
    # WRITER V4 REQUEST
    # =====================================================

    validation_request = (
        build_final_validation_request(
            draft=generated_draft,
            confirmed_facts=(
                confirmed_facts
            ),
        )
    )

    if (
        validation_request.get(
            "status"
        )
        != (
            "READY_FOR_FINAL_VALIDATION"
        )
    ):
        return stop_result(
            status=(
                validation_request.get(
                    "status",
                    (
                        "BLOCKED_FINAL_"
                        "VALIDATION_REQUEST"
                    ),
                )
            ),
            reason=(
                "Final factual validator "
                "was not allowed to run."
            ),
            topic=topic_name,
        )

    # =====================================================
    # WRITER V4 AI VALIDATOR
    # =====================================================

    print(
        "Running final factual validator..."
    )

    validation = (
        run_final_validator(
            validation_request
        )
    )

    print(
        "Validator status:",
        validation.get(
            "status",
        ),
    )

    if (
        validation.get(
            "status"
        )
        != "VALIDATION_PASSED"
    ):
        return stop_result(
            status=(
                validation.get(
                    "status",
                    "BLOCKED_VALIDATION",
                )
            ),
            reason=(
                "Article failed final "
                "factual validation."
            ),
            topic=topic_name,
        )

    # =====================================================
    # FINALIZE VALIDATED DRAFT
    # =====================================================

    validated_draft = (
        finalize_validated_draft(
            draft=generated_draft,
            validation=validation,
        )
    )

    if (
        validated_draft.get(
            "status"
        )
        != "VALIDATED_DRAFT"
    ):
        return stop_result(
            status=(
                validated_draft.get(
                    "status",
                    "BLOCKED_FINAL_GATE",
                )
            ),
            reason=(
                "Final deterministic safety "
                "gate rejected the article."
            ),
            topic=topic_name,
        )

    if (
        validated_draft.get(
            "publishable"
        )
        is not True
    ):
        return stop_result(
            status=(
                "BLOCKED_NOT_PUBLISHABLE"
            ),
            reason=(
                "Validated article did not "
                "receive publishable=True."
            ),
            topic=topic_name,
        )

    print("")
    print(
        "FINAL VALIDATION: PASSED"
    )

    print(
        "Public publishing: DISABLED"
    )

    print(
        "WordPress mode: DRAFT ONLY"
    )

    # =====================================================
    # SAFE REAL WORDPRESS DRAFT
    # =====================================================

    wordpress_result = (
        create_wordpress_draft(
            validated_draft,
            wp_config,
        )
    )

    if (
        wordpress_result.get(
            "status"
        )
        != "WORDPRESS_DRAFT_CREATED"
    ):
        return stop_result(
            status=(
                wordpress_result.get(
                    "status",
                    "BLOCKED_WORDPRESS",
                )
            ),
            reason=(
                "WordPress draft creation "
                "did not complete safely."
            ),
            topic=topic_name,
        )

    result = {
        "status": (
            "PIPELINE_DRAFT_SUCCESS"
        ),
        "topic": topic_name,
        "research_id": (
            research_record.get(
                "id"
            )
        ),
        "confirmed_fact_count": (
            len(
                confirmed_facts
            )
        ),
        "writer_status": (
            generated_draft.get(
                "status"
            )
        ),
        "validator_status": (
            validation.get(
                "status"
            )
        ),
        "final_draft_status": (
            validated_draft.get(
                "status"
            )
        ),
        "title": (
            validated_draft.get(
                "title"
            )
        ),
        "meta_description": (
            validated_draft.get(
                "meta_description"
            )
        ),
        "wordpress_status": (
            "draft"
        ),
        "wordpress_post_id": (
            wordpress_result.get(
                "wordpress_post_id"
            )
        ),
        "wordpress_url": (
            wordpress_result.get(
                "wordpress_url"
            )
        ),

        # Important:
        # this end-to-end test is NEVER public.
        "published": False,

        "created_at": utc_now(),
    }

    save_json(
        PIPELINE_RESULT_FILE,
        result,
    )

    print("")
    print("=" * 60)
    print("END-TO-END PIPELINE SUCCESS")
    print("=" * 60)

    print(
        "Topic:",
        topic_name,
    )

    print(
        "WordPress Post ID:",
        result[
            "wordpress_post_id"
        ],
    )

    print(
        "WordPress status:",
        result[
            "wordpress_status"
        ],
    )

    print(
        "Publicly published:",
        result[
            "published"
        ],
    )

    print("=" * 60)

    return result


# =========================================================
# FULL PIPELINE
# =========================================================

def main():
    print("")
    print("=" * 60)
    print(
        "GAMERQUEST TRENDING SEO"
    )
    print(
        "END-TO-END PIPELINE"
    )
    print("=" * 60)

    print(
        "MODE: MANUAL SAFE TEST"
    )

    print(
        "WORDPRESS: DRAFT ONLY"
    )

    print(
        "PUBLIC AUTO-PUBLISH: OFF"
    )

    print("=" * 60)

    # =====================================================
    # ENVIRONMENT CHECK
    # =====================================================

    if not safe_string(
        os.environ.get(
            "GROQ_API_KEY",
            "",
        )
    ):
        stop_result(
            status=(
                "BLOCKED_MISSING_GROQ_KEY"
            ),
            reason=(
                "GROQ_API_KEY is missing."
            ),
        )

        return

    wp_config = (
        get_wordpress_config()
    )

    if not wp_config:
        stop_result(
            status=(
                "BLOCKED_WORDPRESS_CONFIG"
            ),
            reason=(
                "WordPress credentials "
                "are missing."
            ),
        )

        return

    # =====================================================
    # STAGE 1 — SCORER
    # =====================================================

    print("")
    print("=" * 60)
    print("STAGE 1 — SCORER")
    print("=" * 60)

    try:
        scorer.main()

    except Exception as error:
        stop_result(
            status=(
                "BLOCKED_SCORER_ERROR"
            ),
            reason=(
                f"{type(error).__name__}: "
                f"{error}"
            ),
        )

        return

    # =====================================================
    # STAGE 2 — RESEARCHER
    # =====================================================

    print("")
    print("=" * 60)
    print("STAGE 2 — RESEARCHER")
    print("=" * 60)

    try:
        researcher.main()

    except Exception as error:
        stop_result(
            status=(
                "BLOCKED_RESEARCHER_ERROR"
            ),
            reason=(
                f"{type(error).__name__}: "
                f"{error}"
            ),
        )

        return

    # =====================================================
    # STAGE 3 — LOAD VERIFIED RESEARCH
    # =====================================================

    if not RESEARCH_FILE.exists():
        stop_result(
            status=(
                "BLOCKED_NO_RESEARCH_FILE"
            ),
            reason=(
                "Research results file "
                "was not created."
            ),
        )

        return

    try:
        research_data = load_json(
            RESEARCH_FILE
        )

    except Exception as error:
        stop_result(
            status=(
                "BLOCKED_INVALID_RESEARCH_FILE"
            ),
            reason=(
                f"{type(error).__name__}: "
                f"{error}"
            ),
        )

        return

    candidates = (
        get_safe_research_candidates(
            research_data
        )
    )

    if not candidates:
        stop_result(
            status=(
                "SAFE_STOP_NO_CONFIRMED_FACTS"
            ),
            reason=(
                "No research topic currently "
                "has source-backed confirmed "
                "facts. No article was created."
            ),
        )

        return

    # Only one article in this manual test.
    research_record = (
        candidates[0]
    )

    # =====================================================
    # STAGES 4–7
    # WRITER + VALIDATOR + SAFE WP DRAFT
    # =====================================================

    process_research_topic(
        research_record=(
            research_record
        ),
        wp_config=wp_config,
    )


if __name__ == "__main__":
    main()

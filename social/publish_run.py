import json
import os
import time
import urllib.request
from pathlib import Path

from social.meta_publisher import (
    build_caption,
    load_publish_history,
    save_publish_history,
    pending_platforms,
    mark_platform_published,
    mark_platform_failed,
    publish_instagram_carousel,
    publish_facebook_carousel,
)


DEFAULT_OUTPUT_FILE = Path("social-output.json")
DEFAULT_READY_FILE = Path("social-publish-ready.json")
DEFAULT_HISTORY_FILE = Path("social/publish_history.json")

PUBLIC_URL_ATTEMPTS = 6
PUBLIC_URL_WAIT_SECONDS = 10


# =========================================================
# HELPERS
# =========================================================

def _clean(value):
    if value is None:
        return ""

    return str(value).strip()


def _require_env(name):
    value = _clean(
        os.getenv(name)
    )

    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}"
        )

    return value


def _load_json(path):
    path = Path(path)

    if not path.exists():
        raise RuntimeError(
            f"Required file does not exist: {path}"
        )

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            payload = json.load(file)

    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"Invalid JSON file: {path}"
        ) from error

    if not isinstance(payload, dict):
        raise RuntimeError(
            f"{path} must contain a JSON object."
        )

    return payload


# =========================================================
# PUBLISH PACKAGE
# =========================================================

def extract_publish_package(
    social_output,
    publish_ready,
):
    if not isinstance(
        social_output,
        dict,
    ):
        raise RuntimeError(
            "social-output.json is invalid."
        )

    if not isinstance(
        publish_ready,
        dict,
    ):
        raise RuntimeError(
            "social-publish-ready.json is invalid."
        )

    if (
        social_output.get("status")
        != "ready"
    ):
        raise RuntimeError(
            "Social output is not ready for publishing."
        )

    output_source_id = _clean(
        social_output.get(
            "source_id"
        )
    )

    ready_source_id = _clean(
        publish_ready.get(
            "source_id"
        )
    )

    if not output_source_id:
        raise RuntimeError(
            "social-output.json has no source_id."
        )

    if not ready_source_id:
        raise RuntimeError(
            "social-publish-ready.json has no source_id."
        )

    if (
        output_source_id
        != ready_source_id
    ):
        raise RuntimeError(
            "Source ID mismatch between "
            "social output and prepared images."
        )

    image_urls = publish_ready.get(
        "image_urls",
        [],
    )

    if not isinstance(
        image_urls,
        list,
    ):
        raise RuntimeError(
            "image_urls must be a list."
        )

    image_urls = [
        _clean(url)
        for url in image_urls
        if _clean(url)
    ]

    if len(image_urls) != 3:
        raise RuntimeError(
            "Exactly three prepared image URLs "
            "are required."
        )

    caption = build_caption(
        social_output.get(
            "caption",
            "",
        ),
        social_output.get(
            "hashtags",
            [],
        ),
    )

    return {
        "source_id":
            output_source_id,

        "image_urls":
            image_urls,

        "caption":
            caption,
    }


# =========================================================
# PUBLIC IMAGE CHECK
# =========================================================

def _url_is_public(url):
    try:
        request = urllib.request.Request(
            url,
            method="HEAD",
            headers={
                "User-Agent":
                    "GamerQuest-Social-Publisher/1.0"
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=20,
        ) as response:
            return (
                200
                <= response.status
                < 400
            )

    except Exception:
        return False


def wait_for_public_urls(
    image_urls,
    attempts=PUBLIC_URL_ATTEMPTS,
    wait_seconds=PUBLIC_URL_WAIT_SECONDS,
):
    print(
        "Checking that Meta can access "
        "the three public carousel images..."
    )

    for attempt in range(
        1,
        attempts + 1,
    ):
        unavailable = [
            url
            for url in image_urls
            if not _url_is_public(url)
        ]

        if not unavailable:
            print(
                "All three carousel images "
                "are publicly available."
            )

            return True

        print(
            f"Public image check "
            f"{attempt}/{attempts}: "
            f"{len(unavailable)} image(s) "
            "not available yet."
        )

        if attempt < attempts:
            time.sleep(
                wait_seconds
            )

    raise RuntimeError(
        "The prepared carousel images are "
        "not publicly available yet. "
        "Publishing stopped before contacting Meta."
    )


# =========================================================
# MAIN PUBLISH ORCHESTRATION
# =========================================================

def run_publish(
    output_file=DEFAULT_OUTPUT_FILE,
    ready_file=DEFAULT_READY_FILE,
    history_file=DEFAULT_HISTORY_FILE,
    wait_for_urls=True,
):
    print("")
    print(
        "======================================"
    )
    print(
        "GAMERQUEST META PUBLISHER"
    )
    print(
        "======================================"
    )

    social_output = _load_json(
        output_file
    )

    publish_ready = _load_json(
        ready_file
    )

    package = extract_publish_package(
        social_output,
        publish_ready,
    )

    source_id = package[
        "source_id"
    ]

    image_urls = package[
        "image_urls"
    ]

    caption = package[
        "caption"
    ]

    history = load_publish_history(
        history_file
    )

    pending = pending_platforms(
        source_id,
        history,
    )

    print(
        f"Source ID: {source_id}"
    )

    print(
        "Pending platforms: "
        + (
            ", ".join(pending)
            if pending
            else "none"
        )
    )

    if not pending:
        print(
            "This carousel has already been "
            "published to Instagram and Facebook."
        )

        return {
            "status":
                "already_published",

            "source_id":
                source_id,
        }

    if wait_for_urls:
        wait_for_public_urls(
            image_urls
        )

    results = {
        "status":
            "publishing",

        "source_id":
            source_id,
    }

    errors = []

    # =====================================================
    # INSTAGRAM
    # =====================================================

    if "instagram" in pending:
        print("")
        print(
            "Publishing to Instagram..."
        )

        try:
            ig_access_token = (
                _require_env(
                    "META_IG_ACCESS_TOKEN"
                )
            )

            ig_user_id = (
                _require_env(
                    "META_IG_USER_ID"
                )
            )

            result = (
                publish_instagram_carousel(
                    image_urls=image_urls,
                    caption=caption,
                    ig_user_id=ig_user_id,
                    access_token=(
                        ig_access_token
                    ),
                )
            )

            history = (
                mark_platform_published(
                    history,
                    source_id,
                    "instagram",
                    result.get(
                        "post_id",
                        "",
                    ),
                )
            )

            # Save immediately.
            # If Facebook fails later,
            # Instagram will NOT be duplicated.
            save_publish_history(
                history,
                history_file,
            )

            results[
                "instagram"
            ] = result

            print(
                "Instagram published successfully."
            )

            print(
                "Instagram media ID: "
                f"{result.get('post_id', '')}"
            )

        except Exception as error:
            history = (
                mark_platform_failed(
                    history,
                    source_id,
                    "instagram",
                    str(error),
                )
            )

            save_publish_history(
                history,
                history_file,
            )

            errors.append(
                (
                    "Instagram failed: "
                    f"{error}"
                )
            )

            print(
                f"Instagram failed: {error}"
            )

    else:
        print(
            "Instagram already published. "
            "Skipping."
        )

    # =====================================================
    # FACEBOOK
    # =====================================================

    if "facebook" in pending:
        print("")
        print(
            "Publishing to Facebook..."
        )

        try:
            fb_access_token = (
                _require_env(
                    "META_FB_PAGE_ACCESS_TOKEN"
                )
            )

            page_id = (
                _require_env(
                    "META_PAGE_ID"
                )
            )

            result = (
                publish_facebook_carousel(
                    image_urls=image_urls,
                    caption=caption,
                    page_id=page_id,
                    access_token=(
                        fb_access_token
                    ),
                )
            )

            history = (
                mark_platform_published(
                    history,
                    source_id,
                    "facebook",
                    result.get(
                        "post_id",
                        "",
                    ),
                )
            )

            save_publish_history(
                history,
                history_file,
            )

            results[
                "facebook"
            ] = result

            print(
                "Facebook published successfully."
            )

            print(
                "Facebook post ID: "
                f"{result.get('post_id', '')}"
            )

        except Exception as error:
            history = (
                mark_platform_failed(
                    history,
                    source_id,
                    "facebook",
                    str(error),
                )
            )

            save_publish_history(
                history,
                history_file,
            )

            errors.append(
                (
                    "Facebook failed: "
                    f"{error}"
                )
            )

            print(
                f"Facebook failed: {error}"
            )

    else:
        print(
            "Facebook already published. "
            "Skipping."
        )

    # =====================================================
    # RESULT
    # =====================================================

    if errors:
        results[
            "status"
        ] = "partial_failure"

        results[
            "errors"
        ] = errors

        print("")
        print(
            "======================================"
        )
        print(
            "META PUBLISHING PARTIALLY FAILED"
        )
        print(
            "======================================"
        )

        raise RuntimeError(
            " | ".join(errors)
        )

    results[
        "status"
    ] = "published"

    print("")
    print(
        "======================================"
    )
    print(
        "META PUBLISHING SUCCESS"
    )
    print(
        "======================================"
    )

    return results


def main():
    run_publish()


if __name__ == "__main__":
    main()

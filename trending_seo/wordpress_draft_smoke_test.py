import json
import os
import sys

import requests


def get_required_env(name):
    value = str(
        os.environ.get(name, "")
    ).strip()

    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}"
        )

    return value


def main():
    print("=" * 60)
    print("GAMERQUEST TRENDING SEO")
    print("WORDPRESS DRAFT CONNECTION TEST")
    print("=" * 60)

    wp_url = get_required_env(
        "WP_URL"
    ).rstrip("/")

    wp_username = get_required_env(
        "WP_USERNAME"
    )

    wp_password = get_required_env(
        "WP_APP_PASSWORD"
    )

    endpoint = (
        wp_url
        + "/wp-json/wp/v2/posts"
    )

    payload = {
        "title": (
            "GamerQuest Trending SEO "
            "Connection Test"
        ),
        "content": (
            "<p>This is a controlled "
            "WordPress connection test "
            "for the GamerQuest Trending "
            "SEO automation.</p>"
            "<p>This post must remain "
            "a draft and must not be "
            "published automatically.</p>"
        ),
        "excerpt": (
            "Controlled Trending SEO "
            "WordPress draft test."
        ),

        # CRITICAL SAFETY RULE:
        # draft only, NEVER publish
        "status": "draft",
    }

    print(
        "Target:",
        endpoint,
    )

    print(
        "Requested WordPress status:",
        payload["status"],
    )

    try:
        response = requests.post(
            endpoint,
            json=payload,
            auth=(
                wp_username,
                wp_password,
            ),
            timeout=30,
            headers={
                "Accept": "application/json",
                "User-Agent": (
                    "GamerQuest-Trending-SEO-"
                    "Draft-Smoke-Test/1.0"
                ),
            },
        )

    except Exception as error:
        print(
            "ERROR: WordPress request failed."
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        sys.exit(1)

    print(
        "HTTP status:",
        response.status_code,
    )

    if (
        response.status_code < 200
        or response.status_code >= 300
    ):
        print(
            "ERROR: WordPress returned "
            "a non-success status."
        )

        print(
            response.text[:1000]
        )

        sys.exit(1)

    try:
        data = response.json()

    except Exception:
        print(
            "ERROR: WordPress response "
            "was not valid JSON."
        )

        sys.exit(1)

    if not isinstance(
        data,
        dict,
    ):
        print(
            "ERROR: Unexpected WordPress "
            "response."
        )

        sys.exit(1)

    post_id = data.get(
        "id"
    )

    post_status = str(
        data.get(
            "status",
            "",
        )
    ).strip().lower()

    link = str(
        data.get(
            "link",
            "",
        )
    ).strip()

    if not post_id:
        print(
            "ERROR: WordPress did not "
            "return a post ID."
        )

        print(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
            )[:2000]
        )

        sys.exit(1)

    # =====================================================
    # CRITICAL SAFETY CHECK
    # =====================================================

    if post_status != "draft":
        print(
            "SAFETY ERROR:"
        )

        print(
            "WordPress created the post "
            f"with status '{post_status}' "
            "instead of 'draft'."
        )

        sys.exit(1)

    print()
    print(
        "WORDPRESS CONNECTION: SUCCESS"
    )

    print(
        "Post ID:",
        post_id,
    )

    print(
        "Post status:",
        post_status,
    )

    print(
        "Post URL:",
        link or "(no public URL yet)",
    )

    print()
    print(
        "SAFETY CHECK PASSED:"
    )

    print(
        "The test post exists only "
        "as a WordPress draft."
    )

    print("=" * 60)


if __name__ == "__main__":
    main()

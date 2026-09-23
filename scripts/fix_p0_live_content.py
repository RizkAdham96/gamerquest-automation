import os
import re

import requests


WP_URL = os.environ["WP_URL"].rstrip("/")
WP_USERNAME = os.environ["WP_USERNAME"]
WP_APP_PASSWORD = os.environ["WP_APP_PASSWORD"]

session = requests.Session()
session.auth = (WP_USERNAME, WP_APP_PASSWORD)
session.headers.update({"User-Agent": "GamerQuest-P0-Content-Fix/1.0"})

# Idempotent: when both known P0 claims are already corrected, this workflow
# verifies the live state and exits successfully without rewriting the posts.


def api(path):
    return f"{WP_URL}/wp-json/wp/v2/{path.lstrip('/')}"


def get_post(slug):
    response = session.get(
        api("posts"),
        params={
            "slug": slug,
            "context": "edit",
            "status": "publish,draft,pending,private,future",
        },
        timeout=45,
    )
    response.raise_for_status()
    posts = response.json()
    if not posts:
        raise RuntimeError(f"Post not found: {slug}")
    return posts[0]


def update_post(post, content):
    # GamerQuest's WordPress stack rejects partial REST updates as
    # "empty_content". Preserve all editable text fields on every correction.
    payload = {
        "title": post.get("title", {}).get("raw", ""),
        "content": content,
        "excerpt": post.get("excerpt", {}).get("raw", ""),
        "status": post.get("status", "publish"),
    }
    response = session.post(
        api(f"posts/{post['id']}"),
        # Some hosts/proxies drop JSON request bodies on authenticated REST
        # writes. WordPress also accepts standard form-encoded post fields.
        data=payload,
        timeout=60,
    )
    if not response.ok:
        raise RuntimeError(
            f"WordPress update failed for post {post['id']} "
            f"({response.status_code}): {response.text[:1000]}"
        )
    return response.json()


def fix_silent_hill():
    slug = "silent-hill-townfall-date-de-sortie"
    post = get_post(slug)
    content = post["content"]["raw"]

    updated = content
    replacements = (
        (
            r'<a[^>]*>\s*Xbox Series\s*</a>\s*[Xx]\s*\|\s*[Ss]',
            "Epic Games Store",
        ),
        (
            r"<li>\s*Xbox Series[^<]*</li>",
            "<li>Epic Games Store</li>",
        ),
        (
            r"Xbox Series\s*[Xx]\s*(?:\||/)\s*[Ss]",
            "Epic Games Store",
        ),
    )
    for pattern, replacement in replacements:
        updated = re.sub(pattern, replacement, updated, flags=re.IGNORECASE)

    if re.search(r"\bxbox\b", updated, flags=re.IGNORECASE):
        raise RuntimeError("Silent Hill Townfall still contains an unsupported Xbox claim.")

    if "Epic Games Store" not in updated:
        # Ensure the verified platform is present even if the original wording differed.
        updated += (
            "<p><strong>Mise à jour factuelle :</strong> les plateformes officiellement "
            "annoncées sont PlayStation 5, Steam et Epic Games Store.</p>"
        )

    if updated != content:
        update_post(post, updated)
        print("Corrected Silent Hill Townfall platform claim.")
    else:
        print("Silent Hill Townfall platform claim already correct.")


def fix_gears():
    slug = "date-de-sortie-gears-of-war-e-day"
    post = get_post(slug)
    content = post["content"]["raw"]

    plain_content = re.sub(r"<[^>]+>", " ", content)
    bad_patterns = (
        r"ne\s+mentionne\s+aucun\s+mode\s+multijoueur",
        r"aucun\s+mode\s+multijoueur",
        r"pas\s+de\s+multijoueur",
    )

    if (
        "Horde Siege" in content
        and "Versus" in content
        and not any(
            re.search(pattern, plain_content, flags=re.IGNORECASE)
            for pattern in bad_patterns
        )
    ):
        print("Gears of War: E-Day multiplayer claim already correct.")
        return

    replacement = (
        "<p>La page officielle Xbox confirme une campagne jouable en solo ou en "
        "coopération à deux, ainsi que des modes multijoueur comprenant Horde Siege "
        "et Versus.</p>"
    )

    risky_paragraph = re.compile(
        r"(?is)(<h2>Gears of War.*?multijoueur.*?</h2>)\s*<p>.*?</p>"
    )
    updated, count = risky_paragraph.subn(
        lambda match: f"{match.group(1)}\n{replacement}",
        content,
        count=1,
    )

    if count == 0 and (
        "Horde Siege" not in updated
        or "Versus" not in updated
    ):
        updated += replacement

    for pattern in bad_patterns:
        if re.search(pattern, updated, flags=re.IGNORECASE):
            raise RuntimeError("Gears article still contains the unsupported multiplayer claim.")

    if "Horde Siege" not in updated or "Versus" not in updated:
        raise RuntimeError("Gears article correction did not add the verified multiplayer modes.")

    if updated != content:
        update_post(post, updated)
        print("Corrected Gears of War: E-Day multiplayer claim.")
    else:
        print("Gears of War: E-Day multiplayer claim already correct.")


def main():
    fix_silent_hill()
    fix_gears()
    print("P0 live content corrections complete.")


if __name__ == "__main__":
    main()

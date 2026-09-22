import os
import re

import requests


WP_URL = os.environ["WP_URL"].rstrip("/")
WP_USERNAME = os.environ["WP_USERNAME"]
WP_APP_PASSWORD = os.environ["WP_APP_PASSWORD"]

session = requests.Session()
session.auth = (WP_USERNAME, WP_APP_PASSWORD)
session.headers.update({"User-Agent": "GamerQuest-P0-Content-Fix/1.0"})


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
    response = session.post(
        api(f"posts/{post['id']}"),
        json={"content": content},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def fix_silent_hill():
    slug = "silent-hill-townfall-date-de-sortie"
    post = get_post(slug)
    content = post["content"]["raw"]

    replacements = (
        (r"Xbox Series X\|S", "Epic Games Store"),
        (r"Xbox Series X/S", "Epic Games Store"),
        (r"Xbox Series", "Epic Games Store"),
    )
    updated = content
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

    replacement = (
        "<p>La page officielle Xbox confirme une campagne jouable en solo ou en "
        "coopération à deux, ainsi que des modes multijoueur comprenant Horde Siege "
        "et Versus.</p>"
    )

    risky_paragraph = re.compile(
        r"(?is)<p>[^<]*(?:ne\s+mentionne\s+aucun\s+mode\s+multijoueur|"
        r"aucun\s+mode\s+multijoueur|pas\s+de\s+multijoueur|"
        r"se\s+concentre\s+sur\s+une\s+campagne\s+solo)[^<]*</p>"
    )
    updated, count = risky_paragraph.subn(replacement, content)

    if count == 0 and (
        "Horde Siege" not in updated
        or "Versus" not in updated
    ):
        updated += replacement

    bad_patterns = (
        r"ne\s+mentionne\s+aucun\s+mode\s+multijoueur",
        r"aucun\s+mode\s+multijoueur",
        r"pas\s+de\s+multijoueur",
    )
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

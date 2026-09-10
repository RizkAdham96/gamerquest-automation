import json
import mimetypes
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests

FEED_PATH = Path("gamerquest-deals-feed.json")
WP_URL = os.environ.get("WP_URL", "").rstrip("/")
WP_USERNAME = os.environ.get("WP_USERNAME", "")
WP_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD", "")

SESSION = requests.Session()
SESSION.auth = (WP_USERNAME, WP_APP_PASSWORD)
SESSION.headers.update({"User-Agent": "GamerQuest-GitHub-Actions/1.0"})


def is_expired(article: dict, now: datetime | None = None) -> bool:
    raw_expiry = (article.get("deal") or {}).get("expires_at")
    if not raw_expiry:
        return False

    expires_at = str(raw_expiry).strip()
    if not expires_at:
        return False

    expires_at = expires_at.replace("Z", "+00:00")
    expiry = datetime.fromisoformat(expires_at)
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)

    return expiry <= (now or datetime.now(timezone.utc))


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:180]


def require_config() -> None:
    missing = [
        name for name, value in {
            "WP_URL": WP_URL,
            "WP_USERNAME": WP_USERNAME,
            "WP_APP_PASSWORD": WP_APP_PASSWORD,
        }.items() if not value
    ]
    if missing:
        raise RuntimeError("Missing WordPress configuration: " + ", ".join(missing))


def api(path: str) -> str:
    return f"{WP_URL}/wp-json/wp/v2/{path.lstrip('/')}"


def existing_post(slug: str):
    response = SESSION.get(
        api("posts"),
        params={"slug": slug, "status": "publish,draft,pending,private,future"},
        timeout=45,
    )
    response.raise_for_status()
    posts = response.json()
    return posts[0] if posts else None


def upload_featured_image(image_info: dict) -> int | None:
    url = (image_info or {}).get("url", "").strip()
    filename = (image_info or {}).get("filename", "featured.jpg").strip() or "featured.jpg"
    if not url:
        return None

    try:
        image_response = requests.get(url, timeout=45)
        image_response.raise_for_status()

        content_type = image_response.headers.get("Content-Type") or mimetypes.guess_type(filename)[0] or "image/jpeg"
        media_response = SESSION.post(
            api("media"),
            data=image_response.content,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": content_type,
            },
            timeout=90,
        )
        media_response.raise_for_status()
        media = media_response.json()
        media_id = int(media["id"])

        details = {}
        if image_info.get("alt"):
            details["alt_text"] = image_info["alt"]
        if image_info.get("caption"):
            details["caption"] = image_info["caption"]
        if image_info.get("description"):
            details["description"] = image_info["description"]
        if details:
            SESSION.post(api(f"media/{media_id}"), json=details, timeout=45).raise_for_status()

        return media_id
    except Exception as exc:
        print(f"WARNING: featured image upload failed: {exc}")
        return None


def publish_article(article: dict) -> str:
    title = str(article.get("title", "")).strip()
    content = str(article.get("content", "")).strip()
    excerpt = str(article.get("excerpt", "")).strip()
    source_id = str(article.get("source_id", "")).strip()

    if not title or not content:
        raise ValueError("Deal article is missing title or content")

    slug = slugify(title)
    if source_id:
        slug = f"{slug}-{source_id[:10]}"

    previous = existing_post(slug)
    if previous:
        print(f"SKIP: already exists: {title} -> {previous.get('link', '')}")
        return "skipped"

    media_id = upload_featured_image(article.get("featured_image") or {})
    payload = {
        "title": title,
        "content": content,
        "excerpt": excerpt,
        "slug": slug,
        "status": "publish",
    }
    if media_id:
        payload["featured_media"] = media_id

    response = SESSION.post(api("posts"), json=payload, timeout=90)
    response.raise_for_status()
    post = response.json()
    print(f"PUBLISHED: {title} -> {post.get('link', '')}")
    return "published"


def main() -> None:
    require_config()
    if not FEED_PATH.exists():
        raise FileNotFoundError(f"Missing feed: {FEED_PATH}")

    data = json.loads(FEED_PATH.read_text(encoding="utf-8"))
    articles = data.get("articles") or []
    if not articles:
        print("No qualifying deals to publish.")
        return

    published = 0
    skipped = 0
    expired = 0
    for article in articles:
        if is_expired(article):
            expired += 1
            print(f"SKIP: expired deal: {article.get('title', '')}")
            continue
        result = publish_article(article)
        published += result == "published"
        skipped += result == "skipped"

    print(
        "WordPress direct publish complete: "
        f"published={published}, skipped={skipped}, expired={expired}"
    )


if __name__ == "__main__":
    main()

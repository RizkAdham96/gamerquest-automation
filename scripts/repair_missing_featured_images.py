import json
import os
from pathlib import Path

import requests
from PIL import Image
from requests.auth import HTTPBasicAuth


NEWS_FEED_FILE = Path("gamerquest-news-feed.json")
NEWS_IMAGES_FOLDER = Path("generated_news_images")
DEFAULT_POST_LIMIT = 30
DEFAULT_MAX_REPAIRS = 12


def wordpress_base_url():
    return os.environ.get("WP_URL", "https://gamerquestfr.com").rstrip("/")


def wordpress_auth():
    username = os.environ.get("WP_USERNAME", "").strip()
    password = os.environ.get("WP_APP_PASSWORD", "").strip()
    if not username or not password:
        raise RuntimeError("WP_USERNAME and WP_APP_PASSWORD are required")
    return HTTPBasicAuth(username, password)


def load_feed_images(feed_path=NEWS_FEED_FILE):
    payload = json.loads(Path(feed_path).read_text(encoding="utf-8"))
    mapping = {}
    for article in payload.get("articles", []):
        slug = str(article.get("slug", "")).strip()
        image = article.get("featured_image") or {}
        filename = str(image.get("filename", "")).strip()
        if slug and filename:
            mapping[slug] = {
                "filename": filename,
                "alt": str(image.get("alt", "")).strip(),
                "caption": str(image.get("caption", "")).strip(),
                "description": str(image.get("description", "")).strip(),
            }
    return mapping


def valid_local_image(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size < 1024:
        return False
    try:
        with Image.open(path) as image:
            image.verify()
        return True
    except Exception:
        return False


def fetch_recent_news_posts(session, base_url, limit=DEFAULT_POST_LIMIT):
    response = session.get(
        f"{base_url}/wp-json/wp/v2/posts",
        params={
            "categories": 2,
            "per_page": limit,
            "orderby": "date",
            "order": "desc",
            "_fields": "id,slug,featured_media,title,link",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def upload_media(session, base_url, image_path, metadata):
    with Path(image_path).open("rb") as handle:
        response = session.post(
            f"{base_url}/wp-json/wp/v2/media",
            files={"file": (Path(image_path).name, handle, "image/jpeg")},
            data={
                "alt_text": metadata.get("alt", ""),
                "caption": metadata.get("caption", ""),
                "description": metadata.get("description", ""),
            },
            timeout=60,
        )
    response.raise_for_status()
    media_id = int(response.json().get("id", 0) or 0)
    if media_id <= 0:
        raise RuntimeError("WordPress media upload returned no media id")
    return media_id


def attach_featured_media(session, base_url, post_id, media_id):
    response = session.post(
        f"{base_url}/wp-json/wp/v2/posts/{post_id}",
        json={"featured_media": media_id},
        timeout=30,
    )
    response.raise_for_status()
    updated = response.json()
    if int(updated.get("featured_media", 0) or 0) != int(media_id):
        raise RuntimeError(
            f"WordPress post {post_id} did not retain featured_media={media_id}"
        )


def repair_missing_featured_images(
    session,
    base_url,
    feed_images,
    images_folder=NEWS_IMAGES_FOLDER,
    post_limit=DEFAULT_POST_LIMIT,
    max_repairs=DEFAULT_MAX_REPAIRS,
):
    posts = fetch_recent_news_posts(session, base_url, post_limit)
    repaired = []
    skipped = []

    for post in posts:
        post_id = int(post.get("id", 0) or 0)
        slug = str(post.get("slug", "")).strip()
        featured_media = int(post.get("featured_media", 0) or 0)

        if not post_id or not slug or featured_media > 0:
            continue

        metadata = feed_images.get(slug)
        if not metadata:
            skipped.append((post_id, slug, "no matching feed image metadata"))
            continue

        image_path = Path(images_folder) / metadata["filename"]
        if not valid_local_image(image_path):
            skipped.append((post_id, slug, "image file missing or invalid"))
            continue

        media_id = upload_media(session, base_url, image_path, metadata)
        attach_featured_media(session, base_url, post_id, media_id)
        repaired.append((post_id, slug, media_id))
        print(f"Repaired featured image: post={post_id} slug={slug} media={media_id}")

        if len(repaired) >= max_repairs:
            break

    return repaired, skipped


def verify_no_repairable_missing_images(session, base_url, feed_images, limit=DEFAULT_POST_LIMIT):
    unresolved = []
    posts = fetch_recent_news_posts(session, base_url, limit)
    for post in posts:
        if int(post.get("featured_media", 0) or 0) > 0:
            continue
        slug = str(post.get("slug", "")).strip()
        metadata = feed_images.get(slug)
        if not metadata:
            continue
        image_path = NEWS_IMAGES_FOLDER / metadata["filename"]
        if valid_local_image(image_path):
            unresolved.append((int(post.get("id", 0) or 0), slug))
    return unresolved


def main():
    base_url = wordpress_base_url()
    feed_images = load_feed_images()

    session = requests.Session()
    session.auth = wordpress_auth()
    session.headers.update({"User-Agent": "GamerQuest-Featured-Image-Repair/1.0"})

    repaired, skipped = repair_missing_featured_images(
        session,
        base_url,
        feed_images,
        post_limit=int(os.environ.get("GQ_FEATURED_IMAGE_POST_LIMIT", DEFAULT_POST_LIMIT)),
        max_repairs=int(os.environ.get("GQ_FEATURED_IMAGE_MAX_REPAIRS", DEFAULT_MAX_REPAIRS)),
    )

    print(f"Featured-image repair completed: repaired={len(repaired)} skipped={len(skipped)}")
    for post_id, slug, reason in skipped:
        print(f"Skipped post={post_id} slug={slug}: {reason}")

    unresolved = verify_no_repairable_missing_images(session, base_url, feed_images)
    if unresolved:
        details = ", ".join(f"{post_id}:{slug}" for post_id, slug in unresolved)
        raise SystemExit(f"Repairable WordPress posts still have no featured image: {details}")


if __name__ == "__main__":
    main()

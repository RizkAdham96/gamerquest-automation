import html
import json
import os
from pathlib import Path

import requests
from PIL import Image
from requests.auth import HTTPBasicAuth


NEWS_FEED_FILE = Path("gamerquest-news-feed.json")
NEWS_IMAGES_FOLDER = Path("generated_news_images")
DEFAULT_POST_LIMIT = 100
DEFAULT_MAX_FEATURED_REPAIRS = 20
DEFAULT_MAX_INLINE_REPAIRS = 100


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


def fetch_recent_posts(session, base_url, limit=DEFAULT_POST_LIMIT):
    response = session.get(
        f"{base_url}/wp-json/wp/v2/posts",
        params={
            "per_page": limit,
            "orderby": "date",
            "order": "desc",
            "_fields": "id,slug,featured_media,title,link",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def fetch_post_for_edit(session, base_url, post_id):
    response = session.get(
        f"{base_url}/wp-json/wp/v2/posts/{post_id}",
        params={
            "context": "edit",
            "_fields": "id,slug,featured_media,title,link,content",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def fetch_media(session, base_url, media_id):
    response = session.get(
        f"{base_url}/wp-json/wp/v2/media/{media_id}",
        params={"_fields": "id,source_url,alt_text,caption"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def featured_media_problem(session, base_url, media_id):
    """Return why a post's featured media is unusable, or "" when it loads.

    A post can carry a featured_media id whose attachment was deleted, has
    no file, or whose file 404s / is not an image. The theme then shows
    no picture even though the id looks fine.
    """
    if int(media_id or 0) <= 0:
        return "no featured_media"
    try:
        response = session.get(
            f"{base_url}/wp-json/wp/v2/media/{media_id}",
            params={"_fields": "id,source_url,mime_type,media_details"},
            timeout=30,
        )
    except Exception as exc:
        return f"media lookup failed: {exc}"
    status = getattr(response, "status_code", 200)
    if status == 404:
        return f"media {media_id} deleted"
    if status >= 400:
        return f"media {media_id} lookup HTTP {status}"
    media = response.json() or {}
    source_url = str(media.get("source_url", "")).strip()
    if not source_url:
        return f"media {media_id} has no file"
    mime = str(media.get("mime_type", "")).lower()
    if mime and not mime.startswith("image/"):
        return f"media {media_id} is {mime}, not an image"
    try:
        file_response = session.get(source_url, timeout=30, stream=True)
    except Exception as exc:
        return f"image file unreachable: {exc}"
    file_status = getattr(file_response, "status_code", 200)
    headers = getattr(file_response, "headers", {}) or {}
    content_type = str(headers.get("Content-Type", "")).lower()
    try:
        file_response.close()
    except Exception:
        pass
    if file_status >= 400:
        return f"image file HTTP {file_status}: {source_url}"
    if content_type and "image" not in content_type:
        return f"image file is {content_type}: {source_url}"
    length = headers.get("Content-Length")
    if length and str(length).isdigit() and int(length) < 1024:
        return f"image file is empty ({length} bytes): {source_url}"
    return ""


def image_file_is_blank(path_or_bytes):
    """True for the plain gradient fallback (almost no edges)."""
    from io import BytesIO
    from PIL import ImageFilter, ImageStat
    try:
        source = BytesIO(path_or_bytes) if isinstance(path_or_bytes, bytes) else path_or_bytes
        with Image.open(source) as image:
            gray = image.convert("L").resize((320, 168))
            return ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES)).mean[0] < 2.0
    except Exception:
        return False


def featured_image_is_blank(session, base_url, media_id):
    try:
        media = session.get(
            f"{base_url}/wp-json/wp/v2/media/{media_id}",
            params={"_fields": "id,source_url"},
            timeout=30,
        ).json() or {}
        source_url = str(media.get("source_url", "")).strip()
        if not source_url:
            return False
        content = session.get(source_url, timeout=60).content
    except Exception:
        return False
    return image_file_is_blank(content)


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
    if getattr(response, "status_code", 200) >= 400:
        print(f"Attach failed: post={post_id} status={response.status_code} body={response.text[:800]}")
    response.raise_for_status()
    updated = response.json()
    if int(updated.get("featured_media", 0) or 0) != int(media_id):
        raise RuntimeError(
            f"WordPress post {post_id} did not retain featured_media={media_id}"
        )


def image_figure_html(source_url, alt_text=""):
    safe_url = html.escape(str(source_url).strip(), quote=True)
    safe_alt = html.escape(str(alt_text).strip(), quote=True)
    return (
        '<figure class="wp-block-image size-large">'
        f'<img src="{safe_url}" alt="{safe_alt}" loading="lazy" decoding="async" />'
        "</figure>"
    )


def inject_image_after_intro(content, figure_html):
    content = str(content or "")
    if "<img" in content.lower():
        return content
    marker = "</p>"
    index = content.lower().find(marker)
    if index == -1:
        return f"{figure_html}\n{content}" if content else figure_html
    insert_at = index + len(marker)
    return f"{content[:insert_at]}\n{figure_html}\n{content[insert_at:]}"


def repair_missing_featured_images(
    session,
    base_url,
    feed_images,
    images_folder=NEWS_IMAGES_FOLDER,
    post_limit=DEFAULT_POST_LIMIT,
    max_repairs=DEFAULT_MAX_FEATURED_REPAIRS,
    check_media=False,
):
    posts = fetch_recent_posts(session, base_url, post_limit)
    repaired = []
    skipped = []

    for post in posts:
        post_id = int(post.get("id", 0) or 0)
        slug = str(post.get("slug", "")).strip()
        featured_media = int(post.get("featured_media", 0) or 0)

        if not post_id or not slug:
            continue
        if featured_media > 0:
            if not check_media:
                continue
            problem = featured_media_problem(session, base_url, featured_media)
            if not problem:
                # The image loads; replace it only when it is the blank
                # fallback and a real local image now exists for the post.
                metadata = feed_images.get(slug)
                local = Path(images_folder) / metadata["filename"] if metadata else None
                if not (
                    local
                    and valid_local_image(local)
                    and not image_file_is_blank(local)
                    and featured_image_is_blank(session, base_url, featured_media)
                ):
                    continue
                problem = "featured image is the blank fallback"
            print(f"Broken featured image: post={post_id} slug={slug}: {problem}")

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


def repair_missing_inline_images(
    session,
    base_url,
    post_limit=DEFAULT_POST_LIMIT,
    max_repairs=DEFAULT_MAX_INLINE_REPAIRS,
):
    """Legacy/manual helper. Inline body images are not required for a WordPress featured image."""
    posts = fetch_recent_posts(session, base_url, post_limit)
    repaired = []
    skipped = []

    for summary in posts:
        post_id = int(summary.get("id", 0) or 0)
        featured_media = int(summary.get("featured_media", 0) or 0)
        slug = str(summary.get("slug", "")).strip()
        if not post_id or featured_media <= 0:
            continue

        post = fetch_post_for_edit(session, base_url, post_id)
        content_obj = post.get("content") or {}
        content = str(content_obj.get("raw") or content_obj.get("rendered") or "")
        if "<img" in content.lower():
            continue

        try:
            media = fetch_media(session, base_url, featured_media)
            source_url = str(media.get("source_url", "")).strip()
            if not source_url:
                skipped.append((post_id, slug, "featured media has no source_url"))
                continue
            alt_text = str(media.get("alt_text", "")).strip()
            title_obj = post.get("title") or {}
            fallback_alt = str(title_obj.get("raw") or title_obj.get("rendered") or "").strip()
            figure = image_figure_html(source_url, alt_text or fallback_alt)
            updated_content = inject_image_after_intro(content, figure)
            response = session.post(
                f"{base_url}/wp-json/wp/v2/posts/{post_id}",
                json={"content": updated_content},
                timeout=30,
            )
            response.raise_for_status()
            repaired.append((post_id, slug, featured_media))
            print(
                f"Repaired inline image: post={post_id} slug={slug} "
                f"featured_media={featured_media}"
            )
        except Exception as exc:
            response = getattr(exc, "response", None)
            if response is not None:
                print(
                    f"Inline repair response: post={post_id} status={response.status_code} "
                    f"body={response.text[:1000]}"
                )
            skipped.append((post_id, slug, f"inline repair failed: {exc}"))

        if len(repaired) >= max_repairs:
            break

    return repaired, skipped


def verify_recent_posts_have_featured_images(
    session,
    base_url,
    limit=DEFAULT_POST_LIMIT,
    check_media=False,
):
    """Return recent posts with no featured image, or (check_media) one that does not load."""
    unresolved = []
    posts = fetch_recent_posts(session, base_url, limit)
    for summary in posts:
        post_id = int(summary.get("id", 0) or 0)
        featured_media = int(summary.get("featured_media", 0) or 0)
        slug = str(summary.get("slug", "")).strip()
        if not post_id:
            continue
        if featured_media <= 0:
            unresolved.append((post_id, slug))
        elif check_media and featured_media_problem(session, base_url, featured_media):
            unresolved.append((post_id, slug))
    return unresolved


def main():
    base_url = wordpress_base_url()
    feed_images = load_feed_images()

    session = requests.Session()
    session.auth = wordpress_auth()
    session.headers.update({"User-Agent": "GamerQuest-Featured-Image-Repair/3.0"})

    featured_repaired, featured_skipped = repair_missing_featured_images(
        session,
        base_url,
        feed_images,
        post_limit=int(os.environ.get("GQ_FEATURED_IMAGE_POST_LIMIT", DEFAULT_POST_LIMIT)),
        max_repairs=int(
            os.environ.get("GQ_FEATURED_IMAGE_MAX_REPAIRS", DEFAULT_MAX_FEATURED_REPAIRS)
        ),
        check_media=True,
    )

    print(
        "Featured image repair completed: "
        f"repaired={len(featured_repaired)} skipped={len(featured_skipped)}"
    )
    for post_id, slug, reason in featured_skipped:
        print(f"Skipped post={post_id} slug={slug}: {reason}")

    unresolved = verify_recent_posts_have_featured_images(
        session,
        base_url,
        int(os.environ.get("GQ_FEATURED_IMAGE_POST_LIMIT", DEFAULT_POST_LIMIT)),
        check_media=True,
    )
    if unresolved:
        details = ", ".join(f"{post_id}:{slug}" for post_id, slug in unresolved)
        raise SystemExit(f"WordPress posts still have no featured image: {details}")


if __name__ == "__main__":
    main()

import mimetypes
import os
import re
import time
import unicodedata

import requests

WP_URL = os.environ.get("WP_URL", "").rstrip("/")
WP_USERNAME = os.environ.get("WP_USERNAME", "")
WP_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD", "")


def slugify(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:150]


def review_slug(record):
    return f"avis-{int(record['appid'])}-{slugify(record['name'])}"


def build_post_payload(record, category_id, media_id=None):
    payload = {
        "title": f"{record['name']} : avis joueurs, note et verdict",
        "content": record["content"],
        "excerpt": record["excerpt"],
        "slug": review_slug(record),
        "status": "publish",
        "categories": [int(category_id)],
    }
    if media_id:
        payload["featured_media"] = int(media_id)
    return payload


class WordPressPublisher:
    def __init__(
        self,
        base_url=WP_URL,
        username=WP_USERNAME,
        password=WP_APP_PASSWORD,
        session=None,
        sleep_fn=time.sleep,
        max_attempts=4,
    ):
        if not base_url or not username or not password:
            raise RuntimeError("Missing WP_URL, WP_USERNAME or WP_APP_PASSWORD")
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.session.auth = (username, password)
        self.session.headers.update({
            "User-Agent": "GamerQuest-Reviews/1.1",
            "Connection": "close",
            "Accept": "application/json",
        })
        self.sleep_fn = sleep_fn
        self.max_attempts = max(1, int(max_attempts))

    def api(self, path):
        return f"{self.base_url}/wp-json/wp/v2/{path.lstrip('/')}"

    def _request(self, method, path, **kwargs):
        url = self.api(path)
        transient_errors = (
            requests.ConnectionError,
            requests.Timeout,
            requests.exceptions.ChunkedEncodingError,
        )

        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.session.request(method, url, **kwargs)
                response.raise_for_status()
                return response
            except transient_errors as exc:
                if attempt >= self.max_attempts:
                    raise
                wait_seconds = min(12, attempt * 3)
                print(
                    f"WARNING: WordPress {method.upper()} connection failed "
                    f"(attempt {attempt}/{self.max_attempts}): {exc}. "
                    f"Retrying in {wait_seconds}s."
                )
                self.sleep_fn(wait_seconds)

        raise RuntimeError("WordPress request retry loop ended unexpectedly")

    def tests_category_id(self):
        response = self._request(
            "GET",
            "categories",
            params={"slug": "tests"},
            timeout=45,
        )
        categories = response.json()
        if not categories:
            raise RuntimeError("WordPress category slug 'tests' was not found")
        return int(categories[0]["id"])

    def existing_post(self, slug):
        response = self._request(
            "GET",
            "posts",
            params={"slug": slug, "status": "publish,draft,pending,private,future"},
            timeout=45,
        )
        posts = response.json()
        return posts[0] if posts else None

    def upload_image(self, image_url, filename):
        if not image_url:
            return None
        try:
            source = requests.get(
                image_url,
                timeout=45,
                headers={"User-Agent": "GamerQuest-Reviews/1.1"},
            )
            source.raise_for_status()
            content_type = source.headers.get("Content-Type") or mimetypes.guess_type(filename)[0] or "image/jpeg"
            response = self._request(
                "POST",
                "media",
                data=source.content,
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Content-Type": content_type,
                    "Connection": "close",
                },
                timeout=90,
            )
            return int(response.json()["id"])
        except Exception as exc:
            print(f"WARNING: review image upload failed: {exc}")
            return None

    def publish(self, record):
        category_id = self.tests_category_id()
        slug = review_slug(record)
        existing = self.existing_post(slug)
        media_id = None
        if not existing or not existing.get("featured_media"):
            media_id = self.upload_image(record.get("image_url"), f"steam-{record['appid']}.jpg")
        payload = build_post_payload(record, category_id, media_id)
        if existing:
            response = self._request(
                "POST",
                f"posts/{existing['id']}",
                json=payload,
                timeout=90,
            )
            action = "UPDATED"
        else:
            response = self._request(
                "POST",
                "posts",
                json=payload,
                timeout=90,
            )
            action = "PUBLISHED"
        post = response.json()
        print(f"{action}: {record['name']} -> {post.get('link', '')}")
        return post

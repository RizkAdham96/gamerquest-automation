from pathlib import Path

from PIL import Image

from scripts.repair_missing_featured_images import (
    image_figure_html,
    inject_image_after_intro,
    repair_missing_featured_images,
    repair_missing_inline_images,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.attached = {}
        self.uploads = 0

    def get(self, url, params=None, timeout=None):
        return FakeResponse(
            [
                {"id": 101, "slug": "missing-image", "featured_media": 0},
                {"id": 102, "slug": "already-good", "featured_media": 77},
            ]
        )

    def post(self, url, files=None, data=None, json=None, timeout=None):
        if url.endswith("/wp-json/wp/v2/media"):
            self.uploads += 1
            return FakeResponse({"id": 501})
        post_id = int(url.rstrip("/").split("/")[-1])
        media_id = int(json["featured_media"])
        self.attached[post_id] = media_id
        return FakeResponse({"id": post_id, "featured_media": media_id})


def test_repairs_only_posts_missing_featured_media(tmp_path):
    image_path = tmp_path / "missing-image.jpg"
    Image.new("RGB", (1200, 630), (20, 20, 20)).save(image_path, "JPEG")

    session = FakeSession()
    feed_images = {
        "missing-image": {
            "filename": "missing-image.jpg",
            "alt": "Missing image article",
            "caption": "",
            "description": "",
        },
        "already-good": {
            "filename": "missing-image.jpg",
            "alt": "Already good",
            "caption": "",
            "description": "",
        },
    }

    repaired, skipped = repair_missing_featured_images(
        session,
        "https://example.test",
        feed_images,
        images_folder=Path(tmp_path),
    )

    assert repaired == [(101, "missing-image", 501)]
    assert skipped == []
    assert session.uploads == 1
    assert session.attached == {101: 501}


def test_injects_featured_image_after_first_paragraph():
    content = "<p>Intro text.</p><h2>Next section</h2><p>Body.</p>"
    figure = image_figure_html(
        "https://example.test/image.jpg",
        'Game "cover"',
    )

    updated = inject_image_after_intro(content, figure)

    assert updated.startswith("<p>Intro text.</p>\n<figure")
    assert 'src="https://example.test/image.jpg"' in updated
    assert 'alt="Game &quot;cover&quot;"' in updated
    assert updated.count("<img") == 1


def test_does_not_duplicate_existing_inline_image():
    content = '<p>Intro.</p><figure><img src="existing.jpg" alt=""></figure>'
    figure = image_figure_html("https://example.test/new.jpg", "New")

    assert inject_image_after_intro(content, figure) == content


class InlineRepairSession:
    def __init__(self):
        self.update_payload = None

    def get(self, url, params=None, timeout=None):
        if url.endswith("/wp-json/wp/v2/posts"):
            return FakeResponse([
                {"id": 201, "slug": "needs-inline", "featured_media": 701},
            ])
        if url.endswith("/wp-json/wp/v2/posts/201"):
            payload = {
                "id": 201,
                "slug": "needs-inline",
                "featured_media": 701,
                "title": {"raw": "Needs inline image"},
                "content": {"raw": "<p>Intro.</p><p>Body.</p>"},
            }
            if "excerpt" in str((params or {}).get("_fields", "")):
                payload["excerpt"] = {"raw": "Existing excerpt"}
            return FakeResponse(payload)
        if url.endswith("/wp-json/wp/v2/media/701"):
            return FakeResponse({
                "id": 701,
                "source_url": "https://example.test/featured.jpg",
                "alt_text": "Featured image",
                "caption": {"raw": ""},
            })
        raise AssertionError(f"Unexpected GET {url}")

    def post(self, url, files=None, data=None, json=None, timeout=None):
        raise AssertionError("Inline repairs must use PUT for existing posts")

    def put(self, url, files=None, data=None, json=None, timeout=None):
        assert url.endswith("/wp-json/wp/v2/posts/201")
        self.update_payload = json
        return FakeResponse({"id": 201})


def test_inline_repair_preserves_excerpt_in_wordpress_update():
    session = InlineRepairSession()

    repaired, skipped = repair_missing_inline_images(
        session,
        "https://example.test",
        post_limit=1,
        max_repairs=1,
    )

    assert repaired == [(201, "needs-inline", 701)]
    assert skipped == []
    assert session.update_payload["excerpt"] == "Existing excerpt"
    assert "<img" in session.update_payload["content"]

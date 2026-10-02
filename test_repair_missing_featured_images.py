from pathlib import Path

from PIL import Image

from scripts.repair_missing_featured_images import repair_missing_featured_images


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

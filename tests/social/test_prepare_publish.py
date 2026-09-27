import json
import os
import tempfile
import unittest
from pathlib import Path

from social.prepare_publish import prepare_carousel_for_publish
from social.recover_prepared_publish import prepare_recovery_files
from social.wordpress_media import cleanup_media, stage_carousel_media


class _FakeResponse:
    def __init__(self, payload, status_code=201):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self):
        self.posts = []
        self.deletes = []

    def post(self, url, data, headers, auth, timeout):
        self.posts.append((url, data, headers, auth, timeout))
        index = len(self.posts)
        return _FakeResponse({
            "id": 100 + index,
            "source_url": f"https://gamerquestfr.com/wp-content/uploads/slide-{index}.png",
        })

    def delete(self, url, auth, timeout):
        self.deletes.append((url, auth, timeout))
        return _FakeResponse({"deleted": True}, status_code=200)


class TestPreparePublish(unittest.TestCase):
    def _make_rendered(self, root):
        rendered = root / "social-rendered"
        rendered.mkdir()
        for index in range(1, 4):
            (rendered / f"slide-{index}.png").write_bytes(
                f"image-{index}".encode()
            )
        return rendered

    def test_copies_exactly_three_rendered_images(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rendered = self._make_rendered(root)
            published = root / "social-published"
            result = prepare_carousel_for_publish(
                source_id="article-123",
                rendered_dir=rendered,
                published_root=published,
            )
            self.assertEqual(len(result["image_paths"]), 3)
            for path in result["image_paths"]:
                self.assertTrue((root / path).exists())

    def test_manifest_persists_recovery_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rendered = self._make_rendered(root)
            published = root / "social-published"
            social_output = {
                "status": "ready",
                "source_id": "article-456",
                "caption": "Caption de test",
                "hashtags": ["#GamerQuest", "#Gaming"],
            }
            result = prepare_carousel_for_publish(
                source_id="article-456",
                rendered_dir=rendered,
                published_root=published,
                social_output=social_output,
            )
            manifest = root / result["manifest"]
            data = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(data["source_id"], "article-456")
            self.assertEqual(len(data["image_paths"]), 3)
            self.assertTrue(data["prepared_at_utc"].endswith("Z"))
            self.assertEqual(data["social_output"], social_output)

    def test_recovery_rebuilds_publish_files_without_generation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rendered = self._make_rendered(root)
            social_output = {
                "status": "ready",
                "source_id": "article-recovery",
                "caption": "Recovery caption",
                "hashtags": ["#GamerQuest"],
            }
            old_cwd = Path.cwd()
            try:
                os.chdir(root)
                prepare_carousel_for_publish(
                    source_id="article-recovery",
                    rendered_dir=Path("social-rendered"),
                    published_root=Path("social-published"),
                    social_output=social_output,
                )
                result = prepare_recovery_files(
                    repository="RizkAdham96/gamerquest-automation",
                    branch="main",
                )
                self.assertTrue(result["ready"])
                rebuilt_output = json.loads(Path("social-output.json").read_text(encoding="utf-8"))
                rebuilt_ready = json.loads(Path("social-publish-ready.json").read_text(encoding="utf-8"))
                self.assertEqual(rebuilt_output["caption"], "Recovery caption")
                self.assertEqual(rebuilt_ready["source_id"], "article-recovery")
                self.assertEqual(len(rebuilt_ready["image_urls"]), 3)
            finally:
                os.chdir(old_cwd)

    def test_rejects_missing_images(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rendered = root / "social-rendered"
            published = root / "social-published"
            rendered.mkdir()
            (rendered / "slide-1.png").write_bytes(b"test")
            (rendered / "slide-2.png").write_bytes(b"test")
            with self.assertRaises(ValueError):
                prepare_carousel_for_publish(
                    source_id="article-789",
                    rendered_dir=rendered,
                    published_root=published,
                )

    def test_source_id_is_sanitized_for_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rendered = self._make_rendered(root)
            published = root / "social-published"
            result = prepare_carousel_for_publish(
                source_id="FFVII / News #123",
                rendered_dir=rendered,
                published_root=published,
            )
            self.assertNotIn(" ", result["folder_name"])
            self.assertNotIn("/", result["folder_name"])
            self.assertNotIn("#", result["folder_name"])

    def test_wordpress_staging_returns_three_public_urls_and_media_ids(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rendered = self._make_rendered(root)
            session = _FakeSession()

            result = stage_carousel_media(
                sorted(rendered.glob("slide-*.png")),
                wp_url="https://gamerquestfr.com",
                username="bot",
                app_password="secret",
                session=session,
            )

            self.assertEqual(result["media_ids"], [101, 102, 103])
            self.assertEqual(len(result["image_urls"]), 3)
            self.assertEqual(len(set(result["image_urls"])), 3)
            self.assertEqual(len(session.posts), 3)
            self.assertTrue(all(call[3] == ("bot", "secret") for call in session.posts))

    def test_wordpress_cleanup_deletes_staged_media(self):
        session = _FakeSession()
        cleanup_media(
            [101, 102, 103],
            wp_url="https://gamerquestfr.com",
            username="bot",
            app_password="secret",
            session=session,
        )
        self.assertEqual(len(session.deletes), 3)
        self.assertTrue(all("force=true" in call[0] for call in session.deletes))


if __name__ == "__main__":
    unittest.main()

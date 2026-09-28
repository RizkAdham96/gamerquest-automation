import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from social import config
from social.wordpress_publish import stage_publish_package


class WordPressPublishPackageTests(unittest.TestCase):
    def _ready_output(self):
        return {
            "status": "ready",
            "source_id": "post-123",
            "carousel_version": "v1",
            "caption": "Test caption",
        }

    def _write_rendered(self, root: Path, duplicate=False):
        rendered = root / "rendered"
        rendered.mkdir(parents=True, exist_ok=True)
        blobs = [b"a" * 120_000, b"b" * 120_000, b"c" * 120_000]
        if duplicate:
            blobs[2] = blobs[1]
        for index, blob in enumerate(blobs, start=1):
            (rendered / f"slide-{index}.png").write_bytes(blob)
        return rendered

    def test_stage_requires_ready_social_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(RuntimeError):
                stage_publish_package(
                    social_output={"status": "skipped"},
                    rendered_dir=root,
                    ready_file=root / "ready.json",
                    pending_file=root / "pending.json",
                    wp_url="https://example.test",
                    username="user",
                    app_password="pass",
                )

    def test_stage_requires_source_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = self._ready_output()
            output.pop("source_id")
            with self.assertRaises(RuntimeError):
                stage_publish_package(
                    social_output=output,
                    rendered_dir=root,
                    ready_file=root / "ready.json",
                    pending_file=root / "pending.json",
                    wp_url="https://example.test",
                    username="user",
                    app_password="pass",
                )

    def test_stage_requires_carousel_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = self._ready_output()
            output.pop("carousel_version")
            with self.assertRaises(RuntimeError):
                stage_publish_package(
                    social_output=output,
                    rendered_dir=root,
                    ready_file=root / "ready.json",
                    pending_file=root / "pending.json",
                    wp_url="https://example.test",
                    username="user",
                    app_password="pass",
                )

    def test_stage_rejects_wrong_slide_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rendered = root / "rendered"
            rendered.mkdir()
            (rendered / "slide-1.png").write_bytes(b"a")
            with self.assertRaises(RuntimeError):
                stage_publish_package(
                    social_output=self._ready_output(),
                    rendered_dir=rendered,
                    ready_file=root / "ready.json",
                    pending_file=root / "pending.json",
                    wp_url="https://example.test",
                    username="user",
                    app_password="pass",
                )

    def test_stage_writes_ready_and_pending_manifests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rendered = self._write_rendered(root)
            ready_file = root / "ready.json"
            pending_file = root / "pending.json"
            staged = {
                "image_urls": [f"https://example.test/{i}.png" for i in range(1, 4)],
                "media_ids": [101, 102, 103],
            }

            with patch("social.wordpress_publish.stage_carousel_media", return_value=staged):
                result = stage_publish_package(
                    social_output=self._ready_output(),
                    rendered_dir=rendered,
                    ready_file=ready_file,
                    pending_file=pending_file,
                    wp_url="https://example.test",
                    username="user",
                    app_password="pass",
                )

            self.assertEqual(result["source_id"], "post-123")
            self.assertEqual(len(result["image_urls"]), 3)
            self.assertEqual(json.loads(ready_file.read_text(encoding="utf-8")), result)
            self.assertEqual(json.loads(pending_file.read_text(encoding="utf-8")), result)

    def test_stage_rejects_duplicate_rendered_slides(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rendered = self._write_rendered(root, duplicate=True)
            staged = {
                "image_urls": [f"https://example.test/{i}.png" for i in range(1, 4)],
                "media_ids": [101, 102, 103],
            }

            with patch("social.wordpress_publish.stage_carousel_media", return_value=staged) as upload:
                with self.assertRaises(RuntimeError):
                    stage_publish_package(
                        social_output=self._ready_output(),
                        rendered_dir=rendered,
                        ready_file=root / "ready.json",
                        pending_file=root / "pending.json",
                        wp_url="https://example.test",
                        username="user",
                        app_password="pass",
                    )
                upload.assert_not_called()

    def test_social_schedule_is_three_posts_per_week(self):
        self.assertEqual(config.POSTS_PER_WEEK, 3)

        main_workflow = Path(".github/workflows/social-test.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "30 18 * * 0,2,5"', main_workflow)
        self.assertIn('timezone: "Europe/Paris"', main_workflow)

        sunday_path = Path(".github/workflows/social-sunday.yml")
        self.assertFalse(
            sunday_path.exists(),
            "Sunday should be handled directly by social-test.yml, not a dispatcher workflow",
        )


if __name__ == "__main__":
    unittest.main()

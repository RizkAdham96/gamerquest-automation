import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def load_publish_run():
    spec = importlib.util.find_spec("social.publish_run")
    if spec is None:
        return None
    from social import publish_run
    return publish_run


class TestPublishRun(unittest.TestCase):
    def setUp(self):
        self.publisher = load_publish_run()

    def _write_package(self, directory, version="version-new"):
        output_file = directory / "social-output.json"
        ready_file = directory / "social-publish-ready.json"
        output_file.write_text(json.dumps({
            "status": "ready",
            "source_id": "article-123",
            "caption": "Test caption",
            "hashtags": ["GamerQuest"],
        }), encoding="utf-8")
        ready_file.write_text(json.dumps({
            "source_id": "article-123",
            "carousel_version": version,
            "image_urls": [
                "https://example.com/1.png",
                "https://example.com/2.png",
                "https://example.com/3.png",
            ],
        }), encoding="utf-8")
        return output_file, ready_file

    def test_publish_run_module_exists(self):
        self.assertIsNotNone(self.publisher)

    def test_extract_publish_package_includes_carousel_version(self):
        package = self.publisher.extract_publish_package(
            {"status": "ready", "source_id": "article-123", "caption": "x", "hashtags": []},
            {
                "source_id": "article-123",
                "carousel_version": "sha256-abc",
                "image_urls": [
                    "https://example.com/1.png",
                    "https://example.com/2.png",
                    "https://example.com/3.png",
                ],
            },
        )
        self.assertEqual(package["carousel_version"], "sha256-abc")

    def test_changed_carousel_version_is_pending_even_when_source_was_published(self):
        history = {
            "article-123": {
                "instagram": {"published": True, "post_id": "old", "carousel_version": "version-old"},
                "facebook": {"published": True, "post_id": "oldfb", "carousel_version": "version-old"},
            }
        }
        pending = self.publisher.pending_platforms(
            "article-123", history, carousel_version="version-new"
        )
        self.assertEqual(pending, ["instagram", "facebook"])

    def test_same_carousel_version_is_not_republished(self):
        history = {
            "article-123": {
                "instagram": {"published": True, "post_id": "old", "carousel_version": "version-1"},
                "facebook": {"published": True, "post_id": "oldfb", "carousel_version": "version-1"},
            }
        }
        pending = self.publisher.pending_platforms(
            "article-123", history, carousel_version="version-1"
        )
        self.assertEqual(pending, [])

    def test_legacy_published_history_without_version_remains_skipped(self):
        history = {
            "article-123": {
                "instagram": {"published": True, "post_id": "legacy"},
                "facebook": {"published": True, "post_id": "legacyfb"},
            }
        }
        pending = self.publisher.pending_platforms(
            "article-123", history, carousel_version="version-new"
        )
        self.assertEqual(pending, [])

    def test_successful_publish_records_carousel_version(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            output_file, ready_file = self._write_package(directory, "version-new")
            history_file = directory / "history.json"
            fake_environment = {
                "META_IG_ACCESS_TOKEN": "ig-secret",
                "META_FB_PAGE_ACCESS_TOKEN": "fb-secret",
                "META_IG_USER_ID": "ig-user-123",
                "META_PAGE_ID": "page-123",
            }
            with patch.dict(os.environ, fake_environment, clear=False), \
                 patch.object(self.publisher, "publish_instagram_carousel", return_value={"published": True, "post_id": "ig-new"}), \
                 patch.object(self.publisher, "publish_facebook_carousel", return_value={"published": True, "post_id": "fb-new"}):
                result = self.publisher.run_publish(
                    output_file=output_file,
                    ready_file=ready_file,
                    history_file=history_file,
                    wait_for_urls=False,
                )
            self.assertEqual(result["status"], "published")
            history = json.loads(history_file.read_text(encoding="utf-8"))
            self.assertEqual(history["article-123"]["instagram"]["carousel_version"], "version-new")
            self.assertEqual(history["article-123"]["facebook"]["carousel_version"], "version-new")

    def test_rejects_mismatched_source_ids(self):
        with self.assertRaises(RuntimeError):
            self.publisher.extract_publish_package(
                {"status": "ready", "source_id": "article-a", "caption": "x", "hashtags": []},
                {
                    "source_id": "article-b",
                    "carousel_version": "v1",
                    "image_urls": [
                        "https://example.com/1.png",
                        "https://example.com/2.png",
                        "https://example.com/3.png",
                    ],
                },
            )


if __name__ == "__main__":
    unittest.main()

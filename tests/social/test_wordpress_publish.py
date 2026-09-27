import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from social.wordpress_publish import (
    cleanup_publish_package,
    recover_publish_package,
    stage_publish_package,
)


class WordPressPublishPackageTests(unittest.TestCase):
    def test_stage_recover_cleanup_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rendered = root / "rendered"
            rendered.mkdir()
            for index in range(1, 4):
                (rendered / f"slide-{index}.png").write_bytes((f"slide-{index}-" * 30).encode())

            ready = root / "ready.json"
            pending = root / "pending.json"
            output = root / "output.json"
            social_output = {"status": "ready", "source_id": "source-123", "caption": "ok"}
            staged = {
                "image_urls": [f"https://example.test/{i}.png" for i in range(1, 4)],
                "media_ids": [101, 102, 103],
            }

            with patch("social.wordpress_publish.stage_carousel_media", return_value=staged) as upload:
                package = stage_publish_package(
                    social_output=social_output,
                    rendered_dir=rendered,
                    ready_file=ready,
                    pending_file=pending,
                    wp_url="https://example.test",
                    username="user",
                    app_password="pass",
                )
            self.assertEqual(package["image_urls"], staged["image_urls"])
            self.assertEqual(package["media_ids"], staged["media_ids"])
            self.assertTrue(ready.exists())
            self.assertTrue(pending.exists())
            upload.assert_called_once()

            restored_ready = root / "restored-ready.json"
            recovered = recover_publish_package(
                pending_file=pending,
                output_file=output,
                ready_file=restored_ready,
            )
            self.assertTrue(recovered["ready"])
            self.assertEqual(json.loads(restored_ready.read_text())["image_urls"], staged["image_urls"])

            with patch("social.wordpress_publish.cleanup_media") as cleanup:
                result = cleanup_publish_package(
                    pending_file=pending,
                    wp_url="https://example.test",
                    username="user",
                    app_password="pass",
                )
            self.assertTrue(result["cleaned"])
            self.assertFalse(pending.exists())
            cleanup.assert_called_once_with(
                staged["media_ids"],
                wp_url="https://example.test",
                username="user",
                app_password="pass",
            )


if __name__ == "__main__":
    unittest.main()

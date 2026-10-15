import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from social import config
from social.master_carousel import MASTER_REFERENCE_POST
from social.wordpress_publish import (
    cleanup_publish_package,
    recover_publish_package,
    stage_publish_package,
)


class WordPressPublishPackageTests(unittest.TestCase):
    def _write_rendered(self, root, size=(1080, 1920), duplicate=False):
        rendered = root / "rendered"
        rendered.mkdir()
        colors = [
            (26, 80, 170),
            (100, 35, 180),
            (20, 145, 100),
        ]
        if duplicate:
            colors = [colors[0], colors[0], colors[0]]
        for index, color in enumerate(colors, start=1):
            Image.new("RGB", size, color).save(
                rendered / f"slide-{index:02d}.png",
                format="PNG",
            )
        return rendered

    def _ready_output(self):
        return {
            "status": "ready",
            "source_id": "source-123",
            "fact_checked": True,
            "caption": "ok",
            "carousel": {
                "brand": "GamerQuest",
                "slides": [
                    {
                        "title": "Une actualité gaming importante",
                        "body": "Une explication courte et claire pour les joueurs.",
                    },
                    {
                        "title": "Ce qu'il faut retenir",
                        "body": "Le contexte essentiel tient dans quelques lignes lisibles.",
                    },
                    {
                        "title": "Pourquoi ça compte",
                        "body": "Une conclusion concise qui donne envie de lire la suite.",
                    },
                ],
            },
        }

    def test_master_reference_is_locked(self):
        self.assertEqual(
            MASTER_REFERENCE_POST,
            "https://www.instagram.com/p/Dc9goyhFrV7/?img_index=1",
        )

    def test_recovery_rejects_package_prepared_before_full_slide_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pending = root / "pending.json"
            output = root / "output.json"
            ready = root / "ready.json"
            pending.write_text(json.dumps({
                "source_id": "source-123",
                "carousel_version": "old-contained-images",
                "master_spec_version": "gamerquest-carousel-v1",
                "image_urls": [f"https://example.test/{i}.png" for i in range(1, 4)],
                "social_output": self._ready_output(),
            }))
            with self.assertRaisesRegex(RuntimeError, "pre-master-spec"):
                recover_publish_package(
                    pending_file=pending, output_file=output, ready_file=ready,
                )
            self.assertFalse(output.exists())
            self.assertFalse(ready.exists())

    def test_stage_recover_cleanup_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rendered = self._write_rendered(root)

            ready = root / "ready.json"
            pending = root / "pending.json"
            output = root / "output.json"
            social_output = self._ready_output()
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
            self.assertEqual(package["master_spec_version"], "gamerquest-carousel-v3")
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
            restored = json.loads(restored_ready.read_text())
            self.assertEqual(restored["image_urls"], staged["image_urls"])
            self.assertEqual(restored["master_spec_version"], "gamerquest-carousel-v3")

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

    def test_stage_rejects_copy_that_overflows_master_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rendered = self._write_rendered(root)
            social_output = self._ready_output()
            social_output["carousel"]["slides"][0]["title"] = "Titre beaucoup trop long " * 40
            staged = {
                "image_urls": [f"https://example.test/{i}.png" for i in range(1, 4)],
                "media_ids": [101, 102, 103],
            }

            with patch("social.wordpress_publish.stage_carousel_media", return_value=staged) as upload:
                with self.assertRaises(RuntimeError):
                    stage_publish_package(
                        social_output=social_output,
                        rendered_dir=rendered,
                        ready_file=root / "ready.json",
                        pending_file=root / "pending.json",
                        wp_url="https://example.test",
                        username="user",
                        app_password="pass",
                    )
                upload.assert_not_called()

    def test_stage_rejects_non_master_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rendered = self._write_rendered(root, size=(1080, 1080))
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

    def test_social_schedule_is_two_posts_every_day(self):
        self.assertEqual(config.POSTS_PER_DAY, 2)
        self.assertEqual(config.POSTS_PER_WEEK, 14)

        main_workflow = Path(".github/workflows/social-test.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "30 12,18 * * *"', main_workflow)
        self.assertIn('timezone: "Europe/Paris"', main_workflow)
        recovery = Path(".github/workflows/social-publish-recovery.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "15 13,19 * * *"', recovery)
        self.assertIn('timezone: "Europe/Paris"', recovery)

        sunday_path = Path(".github/workflows/social-sunday.yml")
        self.assertFalse(
            sunday_path.exists(),
            "Sunday should be handled directly by social-test.yml, not a dispatcher workflow",
        )


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path

from social.prepare_publish import (
    prepare_carousel_for_publish,
)


class TestPreparePublish(unittest.TestCase):

    def test_copies_exactly_three_rendered_images(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            rendered = root / "social-rendered"
            published = root / "social-published"
            rendered.mkdir()

            for index in range(1, 4):
                (
                    rendered / f"slide-{index}.png"
                ).write_bytes(
                    f"image-{index}".encode()
                )

            result = prepare_carousel_for_publish(
                source_id="article-123",
                rendered_dir=rendered,
                published_root=published,
            )

            self.assertEqual(
                len(result["image_paths"]),
                3,
            )

            for path in result["image_paths"]:
                self.assertTrue(
                    (root / path).exists()
                )

    def test_creates_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            rendered = root / "social-rendered"
            published = root / "social-published"
            rendered.mkdir()

            for index in range(1, 4):
                (
                    rendered / f"slide-{index}.png"
                ).write_bytes(b"test")

            result = prepare_carousel_for_publish(
                source_id="article-456",
                rendered_dir=rendered,
                published_root=published,
            )

            manifest = Path(
                result["manifest"]
            )

            if not manifest.is_absolute():
                manifest = root / manifest

            self.assertTrue(
                manifest.exists()
            )

            data = json.loads(
                manifest.read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(
                data["source_id"],
                "article-456",
            )

            self.assertEqual(
                len(data["image_paths"]),
                3,
            )

    def test_rejects_missing_images(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            rendered = root / "social-rendered"
            published = root / "social-published"
            rendered.mkdir()

            (
                rendered / "slide-1.png"
            ).write_bytes(b"test")

            (
                rendered / "slide-2.png"
            ).write_bytes(b"test")

            with self.assertRaises(
                ValueError
            ):
                prepare_carousel_for_publish(
                    source_id="article-789",
                    rendered_dir=rendered,
                    published_root=published,
                )

    def test_source_id_is_sanitized_for_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            rendered = root / "social-rendered"
            published = root / "social-published"
            rendered.mkdir()

            for index in range(1, 4):
                (
                    rendered / f"slide-{index}.png"
                ).write_bytes(b"test")

            result = prepare_carousel_for_publish(
                source_id="FFVII / News #123",
                rendered_dir=rendered,
                published_root=published,
            )

            self.assertNotIn(
                " ",
                result["folder_name"],
            )

            self.assertNotIn(
                "/",
                result["folder_name"],
            )

            self.assertNotIn(
                "#",
                result["folder_name"],
            )


if __name__ == "__main__":
    unittest.main()

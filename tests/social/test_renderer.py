import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from social import render, renderer


class TestCarouselRenderer(unittest.TestCase):
    def sample_carousel(self):
        return {
            "brand": "GamerQuest",
            "slides": [
                {
                    "title": f"Slide {index}",
                    "body": "A concise gaming fact that should wrap safely.",
                    "visual_prompt": "gaming visual",
                }
                for index in range(1, 6)
            ],
        }

    def test_render_carousel_creates_five_1080x1350_pngs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = renderer.render_carousel(
                self.sample_carousel(),
                Path(temp_dir),
            )

            self.assertEqual(len(paths), 5)

            for path in paths:
                self.assertTrue(path.exists())
                with Image.open(path) as image:
                    self.assertEqual(image.size, (1080, 1350))
                    self.assertEqual(image.format, "PNG")

    def test_render_carousel_requires_five_slides(self):
        carousel = self.sample_carousel()
        carousel["slides"] = carousel["slides"][:4]

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                renderer.render_carousel(carousel, Path(temp_dir))


class TestRenderCLI(unittest.TestCase):
    def test_render_from_output_requires_ready_fact_checked_payload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "social-output.json"
            output_dir = Path(temp_dir) / "rendered"
            input_path.write_text(
                '{"status":"skipped","fact_checked":false}',
                encoding="utf-8",
            )

            result = render.render_from_output(input_path, output_dir)

            self.assertEqual(result["status"], "skipped")
            self.assertFalse(output_dir.exists())

    def test_render_from_output_writes_manifest(self):
        payload = {
            "status": "ready",
            "fact_checked": True,
            "carousel": {
                "brand": "GamerQuest",
                "caption": "Caption",
                "cta": "Read more",
                "hashtags": ["#GamerQuest"],
                "slides": [
                    {"title": f"Slide {index}", "body": "Body"}
                    for index in range(1, 6)
                ],
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "social-output.json"
            output_dir = Path(temp_dir) / "rendered"
            input_path.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            result = render.render_from_output(input_path, output_dir)
            manifest = json.loads(
                (output_dir / "manifest.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(result["status"], "rendered")
            self.assertEqual(len(manifest["slides"]), 5)
            self.assertEqual(manifest["caption"], "Caption")


if __name__ == "__main__":
    unittest.main()

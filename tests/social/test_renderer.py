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
            paths = renderer.render_carousel(self.sample_carousel(), Path(temp_dir))
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

    def test_renderer_uses_gamerquest_purple_blue_palette(self):
        self.assertEqual(renderer.GQ_PURPLE, (124, 58, 237))
        self.assertEqual(renderer.GQ_BLUE, (56, 189, 248))
        self.assertFalse(hasattr(renderer, "GQ_YELLOW"))
        self.assertFalse(hasattr(renderer, "GQ_ORANGE"))

    def test_render_slide_uses_featured_image_when_available(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "source.png"
            output_path = Path(temp_dir) / "slide.png"
            Image.new("RGB", (500, 500), (20, 180, 80)).save(source_path)
            renderer.render_slide(
                {"title": "Game update", "body": "New content"},
                1,
                5,
                output_path,
                featured_image=str(source_path),
            )
            with Image.open(output_path) as image:
                center = image.getpixel((540, 675))
                self.assertNotEqual(center, renderer.BG)


class TestRenderCLI(unittest.TestCase):
    def test_render_from_output_requires_ready_fact_checked_payload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "social-output.json"
            output_dir = Path(temp_dir) / "rendered"
            input_path.write_text('{"status":"skipped","fact_checked":false}', encoding="utf-8")
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
                "slides": [{"title": f"Slide {index}", "body": "Body"} for index in range(1, 6)],
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "social-output.json"
            output_dir = Path(temp_dir) / "rendered"
            input_path.write_text(json.dumps(payload), encoding="utf-8")
            result = render.render_from_output(input_path, output_dir)
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "rendered")
            self.assertEqual(len(manifest["slides"]), 5)
            self.assertEqual(manifest["caption"], "Caption")

    def test_find_featured_image_url_matches_carousel_topic(self):
        carousel = {"topic": "Scott Pilgrim EX"}
        content = [
            {
                "title": "Scott Pilgrim EX : nouveau DLC",
                "slug": "scott-pilgrim-ex-dlc",
                "featured_image": {"url": "https://example.com/scott.jpg"},
            },
            {
                "title": "LEGO Skylines",
                "featured_image": {"url": "https://example.com/lego.jpg"},
            },
        ]
        self.assertEqual(
            render.find_featured_image_url(carousel, content),
            "https://example.com/scott.jpg",
        )


if __name__ == "__main__":
    unittest.main()

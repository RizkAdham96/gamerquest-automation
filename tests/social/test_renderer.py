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
                    "body": "Une information gaming courte et utile.",
                    "visual_prompt": "gaming visual",
                }
                for index in range(1, 4)
            ],
        }

    def test_render_carousel_creates_three_1080x1350_pngs(self):
        with tempfile.TemporaryDirectory() as temp_dir:

            paths = renderer.render_carousel(
                self.sample_carousel(),
                Path(temp_dir),
            )

            self.assertEqual(len(paths), 3)

            for path in paths:

                self.assertTrue(path.exists())

                with Image.open(path) as image:

                    self.assertEqual(
                        image.size,
                        (1080, 1350),
                    )

                    self.assertEqual(
                        image.format,
                        "PNG",
                    )

    def test_render_carousel_requires_exactly_three_slides(self):

        carousel = self.sample_carousel()

        carousel["slides"] = carousel["slides"][:2]

        with tempfile.TemporaryDirectory() as temp_dir:

            with self.assertRaises(ValueError):

                renderer.render_carousel(
                    carousel,
                    Path(temp_dir),
                )

    def test_renderer_rejects_five_slides(self):

        carousel = self.sample_carousel()

        carousel["slides"].extend(
            [
                {
                    "title": "Extra slide",
                    "body": "Should not exist",
                },
                {
                    "title": "Extra slide",
                    "body": "Should not exist",
                },
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:

            with self.assertRaises(ValueError):

                renderer.render_carousel(
                    carousel,
                    Path(temp_dir),
                )

    def test_renderer_uses_gamerquest_palette(self):

        self.assertEqual(
            renderer.GQ_BLUE,
            (76, 141, 255),
        )

        self.assertEqual(
            renderer.GQ_PURPLE,
            (159, 79, 255),
        )

        self.assertEqual(
            renderer.BG,
            (5, 8, 15),
        )

    def test_renderer_has_no_logo_dependency(self):

        self.assertFalse(
            hasattr(
                renderer,
                "BRAND_LOGO_PNG_BASE64",
            )
        )

        self.assertFalse(
            hasattr(
                renderer,
                "LOGO_PATH",
            )
        )

        self.assertFalse(
            hasattr(
                renderer,
                "_load_brand_logo",
            )
        )

        self.assertFalse(
            hasattr(
                renderer,
                "_draw_logo",
            )
        )

    def test_render_slide_uses_featured_image(self):

        with tempfile.TemporaryDirectory() as temp_dir:

            source_path = (
                Path(temp_dir)
                / "source.png"
            )

            output_path = (
                Path(temp_dir)
                / "slide.png"
            )

            Image.new(
                "RGB",
                (800, 800),
                (20, 180, 80),
            ).save(source_path)

            renderer.render_slide(
                {
                    "title": "Game update",
                    "body": "New content",
                },
                1,
                3,
                output_path,
                featured_image=str(source_path),
            )

            with Image.open(output_path) as image:

                center = image.getpixel(
                    (540, 675)
                )

                self.assertNotEqual(
                    center,
                    renderer.BG,
                )

    def test_renderer_supports_three_distinct_layouts(self):

        layouts = []

        for index in range(1, 4):

            settings = (
                renderer._layout_text_settings(
                    index
                )
            )

            layouts.append(settings)

            self.assertIn(
                "title_y",
                settings,
            )

            self.assertIn(
                "max_width",
                settings,
            )

            self.assertIn(
                "title_size",
                settings,
            )

            self.assertIn(
                "body_size",
                settings,
            )

        self.assertEqual(
            len(layouts),
            3,
        )

    def test_text_layout_stays_inside_canvas(self):

        for index in range(1, 4):

            settings = (
                renderer._layout_text_settings(
                    index
                )
            )

            self.assertGreaterEqual(
                settings["title_y"],
                0,
            )

            self.assertLess(
                settings["title_y"],
                renderer.HEIGHT,
            )

            self.assertGreater(
                settings["max_width"],
                0,
            )

            self.assertLessEqual(
                settings["max_width"],
                renderer.WIDTH,
            )


class TestRenderCLI(unittest.TestCase):

    def test_render_from_output_requires_ready_fact_checked_payload(
        self
    ):

        with tempfile.TemporaryDirectory() as temp_dir:

            input_path = (
                Path(temp_dir)
                / "social-output.json"
            )

            output_dir = (
                Path(temp_dir)
                / "rendered"
            )

            input_path.write_text(
                json.dumps(
                    {
                        "status": "skipped",
                        "fact_checked": False,
                    }
                ),
                encoding="utf-8",
            )

            result = render.render_from_output(
                input_path,
                output_dir,
            )

            self.assertEqual(
                result["status"],
                "skipped",
            )

            self.assertFalse(
                output_dir.exists(),
            )

    def test_render_from_output_writes_three_slide_manifest(
        self
    ):

        payload = {
            "status": "ready",
            "fact_checked": True,
            "carousel": {
                "brand": "GamerQuest",
                "caption": "Caption",
                "cta": "Découvre la suite sur GamerQuest.",
                "hashtags": [
                    "#GamerQuest"
                ],
                "slides": [
                    {
                        "title": f"Slide {index}",
                        "body": "Body",
                    }
                    for index in range(1, 4)
                ],
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:

            input_path = (
                Path(temp_dir)
                / "social-output.json"
            )

            output_dir = (
                Path(temp_dir)
                / "rendered"
            )

            input_path.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            result = render.render_from_output(
                input_path,
                output_dir,
            )

            manifest = json.loads(
                (
                    output_dir
                    / "manifest.json"
                ).read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(
                result["status"],
                "rendered",
            )

            self.assertEqual(
                len(manifest["slides"]),
                3,
            )

            self.assertEqual(
                manifest["caption"],
                "Caption",
            )

            self.assertEqual(
                manifest["cta"],
                "Découvre la suite sur GamerQuest.",
            )

    def test_find_featured_image_url_matches_carousel_topic(
        self
    ):

        carousel = {
            "topic": "Scott Pilgrim EX"
        }

        content = [
            {
                "title":
                    "Scott Pilgrim EX : nouveau DLC",

                "slug":
                    "scott-pilgrim-ex-dlc",

                "featured_image": {
                    "url":
                        "https://example.com/scott.jpg"
                },
            },
            {
                "title": "LEGO Skylines",

                "featured_image": {
                    "url":
                        "https://example.com/lego.jpg"
                },
            },
        ]

        self.assertEqual(
            render.find_featured_image_url(
                carousel,
                content,
            ),
            "https://example.com/scott.jpg",
        )


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from social.master_carousel_spec import (
    MASTER_SPEC_VERSION,
    validate_carousel_copy,
    validate_rendered_carousel,
    validate_renderer_contract,
)


class TestMasterCarouselSpec(unittest.TestCase):
    def sample_carousel(self):
        return {
            "brand": "GamerQuest FR",
            "slides": [
                {
                    "title": "Une grosse actu gaming à retenir",
                    "body": "Voici le contexte essentiel, expliqué rapidement et sans surcharge de texte.",
                },
                {
                    "title": "Ce qui change vraiment",
                    "body": "Le deuxième écran donne les faits utiles sans répéter le premier écran.",
                },
                {
                    "title": "Pourquoi ça compte",
                    "body": "Le dernier écran termine proprement avec une conclusion courte et lisible.",
                },
            ],
        }

    def test_master_spec_has_version(self):
        self.assertTrue(MASTER_SPEC_VERSION)

    def test_renderer_contract_matches_vertical_master_format(self):
        validate_renderer_contract()

    def test_copy_rejects_wrong_slide_count(self):
        carousel = self.sample_carousel()
        carousel["slides"] = carousel["slides"][:2]
        with self.assertRaises(ValueError):
            validate_carousel_copy(carousel)

    def test_copy_rejects_excessive_text_density(self):
        carousel = self.sample_carousel()
        carousel["slides"][1]["body"] = "mot " * 70
        with self.assertRaises(ValueError):
            validate_carousel_copy(carousel)

    def test_copy_rejects_duplicate_slide_text(self):
        carousel = self.sample_carousel()
        carousel["slides"][2] = dict(carousel["slides"][1])
        with self.assertRaises(ValueError):
            validate_carousel_copy(carousel)

    def test_rendered_carousel_requires_three_distinct_1080x1920_pngs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = []
            for index, color in enumerate(((10, 20, 30), (40, 50, 60), (70, 80, 90)), start=1):
                path = root / f"slide-{index:02d}.png"
                Image.new("RGB", (1080, 1920), color).save(path, format="PNG")
                paths.append(path)

            validate_rendered_carousel(paths, min_file_bytes=1000)

    def test_rendered_carousel_rejects_duplicate_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "slide-01.png"
            second = root / "slide-02.png"
            third = root / "slide-03.png"
            Image.new("RGB", (1080, 1920), (10, 20, 30)).save(first, format="PNG")
            second.write_bytes(first.read_bytes())
            Image.new("RGB", (1080, 1920), (70, 80, 90)).save(third, format="PNG")

            with self.assertRaises(ValueError):
                validate_rendered_carousel([first, second, third], min_file_bytes=1000)


if __name__ == "__main__":
    unittest.main()

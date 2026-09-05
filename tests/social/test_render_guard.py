import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from social import render


class TestProductionCreativeGuard(unittest.TestCase):

    def _payload(self):
        return {
            "status": "ready",
            "fact_checked": True,
            "source_id": "article-wolverine",
            "carousel": {
                "source_id": "article-wolverine",
                "brand": "GamerQuest",
                "topic": "Marvel's Wolverine",
                "caption": "Test caption",
                "cta": "Lire la suite sur GamerQuest.fr",
                "hashtags": [
                    "#GamerQuest",
                    "#Gaming",
                ],
                "slides": [
                    {
                        "title": "Marvel's Wolverine arrive",
                        "body": "Une nouvelle aventure sur PS5.",
                    },
                    {
                        "title": "Sortie en septembre",
                        "body": "Le jeu arrive le 15 septembre 2026.",
                    },
                    {
                        "title": "Pas de multijoueur confirmé",
                        "body": (
                            "Aucun mode multijoueur n'a été "
                            "confirmé. Lire la suite sur "
                            "GamerQuest.fr"
                        ),
                    },
                ],
            },
        }

    def _article(self):
        return {
            "source_id": "article-wolverine",
            "title": (
                "Marvel's Wolverine : tout ce qu’il faut "
                "savoir avant sa sortie"
            ),
            "excerpt": "Le prochain jeu d'Insomniac sur PS5.",
        }

    def test_production_stops_when_openai_generation_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)

            input_file = (
                temp_dir
                / "social-output.json"
            )

            output_dir = (
                temp_dir
                / "rendered"
            )

            input_file.write_text(
                json.dumps(
                    self._payload()
                ),
                encoding="utf-8",
            )

            with patch(
                "social.render.get_all_content",
                return_value=[
                    self._article()
                ],
            ), patch(
                "social.render.try_generate_carousel_images",
                return_value=[],
            ), patch(
                "social.render.render_carousel",
            ) as renderer_mock:

                with self.assertRaisesRegex(
                    RuntimeError,
                    "Publishing stopped",
                ):
                    render.render_from_output(
                        input_file,
                        output_dir,
                    )

                renderer_mock.assert_not_called()

    def test_rejects_blank_generated_image(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)

            paths = []

            colors = [
                (255, 255, 255),
                (30, 50, 100),
                (100, 40, 40),
            ]

            for index, color in enumerate(
                colors,
                start=1,
            ):
                path = (
                    temp_dir
                    / f"image-{index}.png"
                )

                Image.new(
                    "RGB",
                    (1024, 1536),
                    color,
                ).save(path)

                paths.append(path)

            with self.assertRaisesRegex(
                RuntimeError,
                "blank",
            ):
                render.validate_generated_images(
                    paths
                )

    def test_rejects_duplicate_generated_images(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)

            paths = []

            for index in range(
                1,
                4,
            ):
                path = (
                    temp_dir
                    / f"image-{index}.png"
                )

                image = Image.new(
                    "RGB",
                    (1024, 1536),
                    (30, 60, 120),
                )

                image.save(path)

                paths.append(path)

            with self.assertRaisesRegex(
                RuntimeError,
                "duplicate",
            ):
                render.validate_generated_images(
                    paths
                )

    def test_three_distinct_images_are_accepted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)

            paths = []

            for index in range(
                1,
                4,
            ):
                path = (
                    temp_dir
                    / f"image-{index}.png"
                )

                image = Image.new(
                    "RGB",
                    (1024, 1536),
                    (
                        30 * index,
                        60 + (index * 20),
                        100 + (index * 30),
                    ),
                )

                # Add distinct geometric content so that
                # the perceptual hashes are different.
                for x in range(
                    index * 50,
                    index * 50 + 250,
                ):
                    for y in range(
                        index * 100,
                        index * 100 + 250,
                    ):
                        if (
                            x < image.width
                            and y < image.height
                        ):
                            image.putpixel(
                                (x, y),
                                (
                                    220 - index * 20,
                                    80 + index * 20,
                                    40 + index * 30,
                                ),
                            )

                image.save(path)
                paths.append(path)

            result = (
                render.validate_generated_images(
                    paths
                )
            )

            self.assertEqual(
                len(result),
                3,
            )

    def test_removes_repeated_gamerquest_cta_from_body(self):
        body = (
            "Aucun mode multijoueur n'a été confirmé. "
            "Plus d’informations sur GamerQuest.fr. "
            "Lire la suite sur GamerQuest.fr"
        )

        cleaned = (
            render.remove_redundant_cta(
                body
            )
        )

        self.assertNotIn(
            "Lire la suite",
            cleaned,
        )

        self.assertNotIn(
            "Plus d’informations",
            cleaned,
        )

        self.assertEqual(
            cleaned,
            (
                "Aucun mode multijoueur "
                "n'a été confirmé."
            ),
        )


if __name__ == "__main__":
    unittest.main()

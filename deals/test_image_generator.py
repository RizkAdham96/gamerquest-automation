import unittest
from unittest.mock import patch

from PIL import Image

from deals.image_generator import generate_deal_image


class TestDealImageTitleRemoved(unittest.TestCase):

    def test_deal_image_does_not_draw_game_title(self):
        source = Image.new(
            "RGB",
            (1600, 900),
            (100, 120, 140),
        )

        deal = {
            "title": "Control",
            "store": "Steam",
            "original_price": 39.99,
            "current_price": 3.99,
            "discount_percent": 90,
            "image_url": "https://example.com/control.jpg",
        }

        with patch(
            "deals.image_generator.download_image",
            return_value=source,
        ):
            with patch(
                "deals.image_generator.ImageDraw.Draw",
                wraps=__import__(
                    "PIL.ImageDraw",
                    fromlist=["ImageDraw"],
                ).Draw,
            ) as draw_factory:

                generate_deal_image(
                    deal,
                    "/tmp/gamerquest-test-deal.jpg",
                )

                drawn_texts = []

                for call in draw_factory.mock_calls:
                    if call.args:
                        for arg in call.args:
                            if isinstance(arg, str):
                                drawn_texts.append(arg)

                self.assertNotIn(
                    "Control",
                    drawn_texts,
                )


if __name__ == "__main__":
    unittest.main()

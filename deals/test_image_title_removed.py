import unittest
from unittest.mock import patch, MagicMock

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

        fake_draw = MagicMock()

        fake_draw.textbbox.return_value = (
            0,
            0,
            180,
            60,
        )

        with patch(
            "deals.image_generator.download_image",
            return_value=source,
        ):
            with patch(
                "deals.image_generator.ImageDraw.Draw",
                return_value=fake_draw,
            ):

                generate_deal_image(
                    deal,
                    "/tmp/gamerquest-test-deal.jpg",
                )

        drawn_texts = []

        for call in fake_draw.text.call_args_list:
            if len(call.args) >= 2:
                drawn_texts.append(
                    str(call.args[1])
                )

        self.assertNotIn(
            "Control",
            drawn_texts,
        )

        # We DO want the deal information to stay.
        self.assertIn(
            "-90%",
            drawn_texts,
        )


if __name__ == "__main__":
    unittest.main()

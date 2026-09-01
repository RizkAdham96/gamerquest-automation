from pathlib import Path

from PIL import Image

from deals.image_generator import generate_deal_image


def test_generates_featured_image(tmp_path):
    deal = {
        "title": "Cardpocalypse Standard Edition",
        "store": "Epic Games Store",
        "original_price": 23.99,
        "current_price": 0,
        "discount_percent": 100,
        "image_url": None,
    }

    output = tmp_path / "deal.jpg"

    result = generate_deal_image(
        deal=deal,
        output_path=output,
    )

    assert result.exists()

    image = Image.open(result)

    assert image.size == (1200, 630)
    assert image.format == "JPEG"
